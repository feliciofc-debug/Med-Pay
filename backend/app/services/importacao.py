"""Importação de planilha → linhas normalizadas.

Responsabilidades:
1. Calcular hash SHA-256 do conteúdo (idempotência)
2. Detectar formato (XLSX, XLS, CSV)
3. Mapear colunas (heurística automática + override do cliente)
4. Retornar lista de `LinhaPlanilha` com dados crus prontos pra validação

REGRA: este serviço NÃO valida CPF/banco/valor. Apenas extrai e normaliza
os dados. Validação acontece em `services/processamento.py`.
"""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.exceptions import (
    LoteFormatoNaoReconhecidoError,
    LoteVazioError,
)


# ============================================================
# Tipos
# ============================================================


@dataclass(slots=True)
class LinhaPlanilha:
    """Uma linha extraída da planilha, ainda crua (sem validação)."""

    numero_linha: int  # 1-indexed (linha do Excel, sem contar header)
    cpf_raw: str | None
    nome_raw: str | None
    banco_raw: str | None
    agencia_raw: str | None
    conta_raw: str | None
    valor_raw: Any  # pode vir como str, float, int

    @property
    def linha_resumo(self) -> str:
        return (
            f"linha {self.numero_linha}: "
            f"nome={self.nome_raw!r} cpf={self.cpf_raw!r} "
            f"valor={self.valor_raw!r}"
        )


@dataclass(slots=True)
class ResultadoImportacao:
    """Resultado bruto da importação de uma planilha."""

    hash_conteudo: str
    nome_arquivo: str
    total_linhas: int
    mapeamento_usado: dict[str, str]
    linhas: list[LinhaPlanilha]


# ============================================================
# Mapeamento heurístico de colunas
# ============================================================

# Aliases comuns que clientes usam pra cada campo lógico.
# A busca é case-insensitive e ignora acentos/espaços/_.
_ALIASES_CAMPO: dict[str, list[str]] = {
    "cpf": [
        "cpf",
        "documento",
        "doc",
        "cpfprestador",
        "cpfbeneficiario",
        "cpfmedico",
        "numerocpf",
    ],
    "nome": [
        "nome",
        "beneficiario",
        "favorecido",
        "prestador",
        "medico",
        "razaosocial",
        "nomecompleto",
        "nomedoprestador",
    ],
    "banco": [
        "banco",
        "codigobanco",
        "bancodestino",
        "codbanco",
        "ban",
    ],
    "agencia": [
        "agencia",
        "ag",
        "agenciadestino",
        "agenciaconta",
    ],
    "conta": [
        "conta",
        "ccdestino",
        "contacorrente",
        "contadestino",
        "ccpoupanca",
        "cc",
    ],
    "valor": [
        "valor",
        "valorr",
        "valorrs",
        "valorreais",
        "valorpagamento",
        "valorbruto",
        "valorliquido",
        "valorpagar",
        "valorrepasse",
        "vlr",
    ],
}


def _normalizar_chave(s: str) -> str:
    """Remove acentos e tudo que não é letra/dígito; lowercase.

    Ex: 'Razão Social' → 'razaosocial', 'Valor R$' → 'valorr',
        'C/C' → 'cc', 'Cód Banco' → 'codbanco'.

    Antes a normalização só removia uma lista pequena de separadores
    (`\\s _ - . / ( )`), o que deixava de fora caracteres como `$`,
    `#`, `*` etc. Agora qualquer coisa que não seja letra ou número é
    removida, deixando o matching com aliases mais resiliente a
    cabeçalhos "criativos" das planilhas dos hospitais.
    """
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", "", sem_acento).lower()


def _detectar_mapeamento(
    colunas_planilha: list[str],
    override_cliente: dict[str, str] | None = None,
) -> dict[str, str]:
    """Mapeia campos lógicos → coluna real da planilha.

    Args:
        colunas_planilha: nomes das colunas como vieram (ex: ["CPF", "Nome", "Valor"])
        override_cliente: mapeamento salvo do cliente (campo_logico → coluna_real)

    Returns:
        Dict {campo_logico: coluna_real}. Campos não encontrados ficam de fora.
    """
    if override_cliente:
        # Se cliente tem mapeamento salvo, prioriza
        return {k: v for k, v in override_cliente.items() if v in colunas_planilha}

    mapeamento: dict[str, str] = {}
    colunas_normalizadas = {_normalizar_chave(c): c for c in colunas_planilha}

    for campo_logico, aliases in _ALIASES_CAMPO.items():
        for alias in aliases:
            alias_norm = _normalizar_chave(alias)
            if alias_norm in colunas_normalizadas:
                mapeamento[campo_logico] = colunas_normalizadas[alias_norm]
                break

    return mapeamento


# ============================================================
# Hash de conteúdo (idempotência)
# ============================================================


def calcular_hash_conteudo(conteudo: bytes) -> str:
    """SHA-256 hex do conteúdo bruto do arquivo."""
    return hashlib.sha256(conteudo).hexdigest()


# ============================================================
# Leitura
# ============================================================


def _detectar_engine(nome_arquivo: str) -> str:
    """Decide qual engine pandas usar pela extensão do arquivo."""
    ext = Path(nome_arquivo).suffix.lower()
    if ext in (".xlsx",):
        return "openpyxl"
    if ext in (".xls",):
        return "xlrd"
    return "csv"


def _ler_planilha(
    conteudo: bytes, nome_arquivo: str
) -> pd.DataFrame:
    """Lê planilha em DataFrame, escolhendo engine pela extensão.

    Raises:
        LoteFormatoNaoReconhecidoError: extensão não suportada ou erro de parsing
    """
    engine = _detectar_engine(nome_arquivo)
    buffer = io.BytesIO(conteudo)

    try:
        if engine == "csv":
            return pd.read_csv(buffer, dtype=str, keep_default_na=False)
        # XLSX/XLS — força leitura como string pra preservar zeros à esquerda
        return pd.read_excel(buffer, engine=engine, dtype=str, keep_default_na=False)
    except Exception as exc:  # pragma: no cover (depende de arquivos corrompidos)
        raise LoteFormatoNaoReconhecidoError(
            f"Não foi possível ler o arquivo {nome_arquivo}: {exc}"
        ) from exc


# ============================================================
# Função principal
# ============================================================


def importar_planilha(
    conteudo: bytes,
    nome_arquivo: str,
    *,
    mapeamento_cliente: dict[str, str] | None = None,
) -> ResultadoImportacao:
    """Importa uma planilha e retorna linhas normalizadas (sem validar conteúdo).

    Args:
        conteudo: bytes do arquivo
        nome_arquivo: nome com extensão (define o parser)
        mapeamento_cliente: mapeamento opcional salvo pra este cliente

    Returns:
        ResultadoImportacao com hash, total de linhas e linhas extraídas

    Raises:
        LoteVazioError: planilha sem linhas de dados
        LoteFormatoNaoReconhecidoError: não conseguiu ler ou mapear colunas
    """
    if not conteudo:
        raise LoteVazioError("Arquivo vazio")

    df = _ler_planilha(conteudo, nome_arquivo)
    if df.empty:
        raise LoteVazioError("Planilha não contém linhas de dados")

    df.columns = [str(c).strip() for c in df.columns]
    mapeamento = _detectar_mapeamento(list(df.columns), mapeamento_cliente)

    obrigatorios = {"cpf", "nome", "valor"}
    faltando = obrigatorios - set(mapeamento.keys())
    if faltando:
        raise LoteFormatoNaoReconhecidoError(
            f"Não foi possível identificar as colunas obrigatórias: {', '.join(sorted(faltando))}. "
            f"Colunas encontradas: {', '.join(df.columns)}"
        )

    def _get(row: pd.Series, campo: str) -> str | None:
        coluna = mapeamento.get(campo)
        if coluna is None:
            return None
        valor = row.get(coluna)
        if valor is None:
            return None
        s = str(valor).strip()
        return s if s else None

    linhas: list[LinhaPlanilha] = []
    for idx, row in df.iterrows():
        # idx é 0-indexed do pandas; +2 = linha real do Excel (header é linha 1)
        numero_linha = int(idx) + 2  # type: ignore[arg-type]
        linha = LinhaPlanilha(
            numero_linha=numero_linha,
            cpf_raw=_get(row, "cpf"),
            nome_raw=_get(row, "nome"),
            banco_raw=_get(row, "banco"),
            agencia_raw=_get(row, "agencia"),
            conta_raw=_get(row, "conta"),
            valor_raw=_get(row, "valor"),
        )
        linhas.append(linha)

    return ResultadoImportacao(
        hash_conteudo=calcular_hash_conteudo(conteudo),
        nome_arquivo=nome_arquivo,
        total_linhas=len(linhas),
        mapeamento_usado=mapeamento,
        linhas=linhas,
    )


__all__ = [
    "LinhaPlanilha",
    "ResultadoImportacao",
    "calcular_hash_conteudo",
    "importar_planilha",
]
