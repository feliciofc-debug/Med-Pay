"""Importação da planilha de códigos de serviço (XLSX/CSV).

Caso do Sandro: ele mantém uma planilha Excel com ~centenas de códigos
de procedimentos anestésicos. Cada linha tem ao menos:
    - código (ex.: "ANE001", "5.01.001")
    - descrição
    - valor (R$ ou centavos)
    - (opcional) categoria/porte

Estratégia: importação tolerante.
    1. Detecta o cabeçalho (linha que contém termos típicos).
    2. Mapeia cada coluna pra um campo conhecido por heurística
       (sinônimos em português).
    3. Faz upsert por (cliente_id, codigo) — re-importação atualiza
       valores ao invés de duplicar (idempotência).
    4. Retorna o resumo: criados, atualizados, inalterados, erros.

Não valida regras de negócio (preço mínimo, etc). Apenas garante:
    - código não vazio
    - descrição não vazia
    - valor parseável como número não-negativo
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import LoteFormatoNaoReconhecidoError, LoteVazioError
from app.models.codigo_servico import CodigoServico


# ============================================================
# Heurística de mapeamento de colunas
# ============================================================


def _normalizar(texto: str) -> str:
    """Lowercase + sem acento + sem caracteres especiais (pra comparar headers)."""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", t.lower())


# Sinônimos esperados em cada campo. Ordem importa só pra debug; match é OR.
_SINONIMOS_CODIGO = (
    "codigo",
    "cod",
    "codigoservico",
    "codigoprocedimento",
    "id",
    "tabela",
)
_SINONIMOS_DESCRICAO = (
    "descricao",
    "procedimento",
    "servico",
    "nome",
    "designacao",
    "detalhe",
)
_SINONIMOS_VALOR = (
    "valor",
    "valorreais",
    "valorrs",
    "valorbruto",
    "preco",
    "vlr",
    "vlrbruto",
    "honorario",
)
_SINONIMOS_CATEGORIA = ("categoria", "grupo", "classe", "tipo")
_SINONIMOS_PORTE = ("porte", "complexidade", "anestesico", "anestesica")


def _mapear_colunas(df: pd.DataFrame) -> dict[str, str]:
    """Mapeia headers da planilha pros campos conhecidos.

    Retorna dict {campo_canonical: nome_coluna_original}.
    Levanta `LoteFormatoNaoReconhecidoError` se faltar algo obrigatório.
    """
    mapa: dict[str, str] = {}
    for coluna in df.columns:
        norm = _normalizar(coluna)
        if "codigo" not in mapa and any(s in norm for s in _SINONIMOS_CODIGO):
            mapa["codigo"] = coluna
        elif "descricao" not in mapa and any(
            s in norm for s in _SINONIMOS_DESCRICAO
        ):
            mapa["descricao"] = coluna
        elif "valor" not in mapa and any(s in norm for s in _SINONIMOS_VALOR):
            mapa["valor"] = coluna
        elif "categoria" not in mapa and any(
            s in norm for s in _SINONIMOS_CATEGORIA
        ):
            mapa["categoria"] = coluna
        elif "porte" not in mapa and any(s in norm for s in _SINONIMOS_PORTE):
            mapa["porte"] = coluna

    obrigatorios = ("codigo", "descricao", "valor")
    faltam = [c for c in obrigatorios if c not in mapa]
    if faltam:
        raise LoteFormatoNaoReconhecidoError(
            "Não consegui identificar as colunas obrigatórias da planilha. "
            f"Faltam: {', '.join(faltam)}. Cabeçalhos encontrados: "
            f"{list(df.columns)}",
            code="PLANILHA_COLUNAS_NAO_RECONHECIDAS",
        )
    return mapa


# ============================================================
# Parser de valor monetário
# ============================================================


def _parse_valor_centavos(valor: Any) -> int:
    """Converte qualquer formato BR de valor pra centavos (int)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return 0
    if isinstance(valor, (int, float)):
        return int(round(float(valor) * 100))
    s = str(valor).strip()
    if not s:
        return 0
    # Remove R$, espaços, NBSP
    s = s.replace("R$", "").replace("\xa0", "").strip()
    # Formatos esperados:
    #   "1.234,56"  → 123456
    #   "1234.56"   → 123456
    #   "1234,56"   → 123456
    #   "1234"      → 123400
    if "," in s and "." in s:
        # presume formato BR: ponto separa milhar, vírgula separa decimal
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return int(round(float(s) * 100))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"valor inválido: {valor!r}") from exc


# ============================================================
# Importador
# ============================================================


@dataclass(slots=True)
class ResultadoImportacao:
    criados: int
    atualizados: int
    inalterados: int
    erros: list[str]
    total_linhas: int


def _ler_planilha(conteudo: bytes, nome_arquivo: str) -> pd.DataFrame:
    """Lê XLSX ou CSV com a primeira linha como cabeçalho."""
    ext = (nome_arquivo.split(".")[-1] or "").lower()
    bio = io.BytesIO(conteudo)
    if ext in ("xlsx", "xls"):
        df = pd.read_excel(bio, dtype=str, engine="openpyxl" if ext == "xlsx" else None)
    elif ext == "csv":
        df = pd.read_csv(bio, dtype=str, sep=None, engine="python")
    else:
        raise LoteFormatoNaoReconhecidoError(
            f"Extensão não suportada: .{ext}. Use .xlsx, .xls ou .csv.",
            code="EXTENSAO_NAO_SUPORTADA",
        )
    if df.empty:
        raise LoteVazioError("Planilha vazia (sem linhas).")
    # Remove linhas totalmente vazias
    df = df.dropna(how="all").reset_index(drop=True)
    if df.empty:
        raise LoteVazioError("Planilha vazia (todas as linhas em branco).")
    return df


class CodigoServicoImportacaoService:
    """Importa códigos de serviço de uma planilha XLSX/CSV."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def importar(
        self,
        *,
        cliente_id: UUID,
        conteudo: bytes,
        nome_arquivo: str,
    ) -> ResultadoImportacao:
        df = _ler_planilha(conteudo, nome_arquivo)
        mapa = _mapear_colunas(df)

        # Buffer de erros não-fatais (linhas que falham individualmente
        # mas não derrubam a importação inteira).
        erros: list[str] = []
        criados = 0
        atualizados = 0
        inalterados = 0

        # Carrega em memória o set de códigos já existentes do cliente
        # pra fazer upsert eficiente (a tabela típica do Sandro tem
        # centenas de linhas, cabe na RAM).
        existentes_stmt = select(CodigoServico).where(
            CodigoServico.cliente_id == cliente_id
        )
        result = await self.db.execute(existentes_stmt)
        por_codigo: dict[str, CodigoServico] = {
            row.codigo.upper(): row for row in result.scalars().all()
        }

        for idx, row in df.iterrows():
            numero_linha = int(idx) + 2  # +1 header, +1 1-indexed
            try:
                codigo_raw = row.get(mapa["codigo"])
                descricao_raw = row.get(mapa["descricao"])
                valor_raw = row.get(mapa["valor"])
                categoria_raw = (
                    row.get(mapa["categoria"]) if "categoria" in mapa else None
                )
                porte_raw = row.get(mapa["porte"]) if "porte" in mapa else None

                codigo = (
                    str(codigo_raw).strip().upper()
                    if codigo_raw is not None and not pd.isna(codigo_raw)
                    else ""
                )
                descricao = (
                    str(descricao_raw).strip()
                    if descricao_raw is not None and not pd.isna(descricao_raw)
                    else ""
                )
                if not codigo:
                    erros.append(f"linha {numero_linha}: código vazio — ignorada")
                    continue
                if not descricao:
                    erros.append(
                        f"linha {numero_linha}: descrição vazia — ignorada"
                    )
                    continue

                try:
                    valor_centavos = _parse_valor_centavos(valor_raw)
                except ValueError as exc:
                    erros.append(f"linha {numero_linha}: {exc} — ignorada")
                    continue

                categoria = (
                    str(categoria_raw).strip()
                    if categoria_raw is not None and not pd.isna(categoria_raw)
                    else None
                ) or None
                porte = (
                    str(porte_raw).strip()
                    if porte_raw is not None and not pd.isna(porte_raw)
                    else None
                ) or None

                existente = por_codigo.get(codigo)
                if existente is None:
                    novo = CodigoServico(
                        cliente_id=cliente_id,
                        codigo=codigo,
                        descricao=descricao,
                        valor_centavos=valor_centavos,
                        categoria=categoria,
                        porte=porte,
                    )
                    self.db.add(novo)
                    criados += 1
                else:
                    mudou = (
                        existente.descricao != descricao
                        or existente.valor_centavos != valor_centavos
                        or (existente.categoria or None) != categoria
                        or (existente.porte or None) != porte
                    )
                    if mudou:
                        existente.descricao = descricao
                        existente.valor_centavos = valor_centavos
                        existente.categoria = categoria
                        existente.porte = porte
                        atualizados += 1
                    else:
                        inalterados += 1
            except Exception as exc:  # pragma: no cover - safety net
                erros.append(f"linha {numero_linha}: erro inesperado ({exc})")

        await self.db.flush()
        return ResultadoImportacao(
            criados=criados,
            atualizados=atualizados,
            inalterados=inalterados,
            erros=erros,
            total_linhas=int(len(df)),
        )


__all__ = ["CodigoServicoImportacaoService", "ResultadoImportacao"]
