"""Importação em massa de participantes da SCP a partir de planilha.

O hospital/empresa de repasse normalmente já tem os médicos e seus
percentuais planilhados. Este serviço lê essa planilha (XLSX/CSV),
identifica as colunas (CPF, nome, percentual) e devolve um PREVIEW
linha-a-linha pra o operador CONFERIR contra a planilha original antes
de gravar. Nada é criado no /preview — só no /confirm.

Reusa a infra que já existe:
    - `_ler_planilha` (services.importacao) pra ler XLSX/CSV
    - `validar_cpf` pra validar/limpar CPF
    - `BeneficiarioService.upsert_de_ficha` pra garantir o médico cadastrado
    - mesmo padrão de token + cache em memória do import de beneficiários

Interpretação do percentual (e por que o preview mostra os dois valores):
    a célula pode vir como "8", "8%", "8,5" ou como fração "0,08". Pra não
    chutar, o serviço detecta o MODO olhando a SOMA da coluna:
        - soma ~1.0  → valores são FRAÇÃO (0,08 = 8%) → multiplica por 100
        - caso contrário → já são PERCENTUAL (8 = 8%)
    O modo detectado vai no preview pra o operador validar; ele pode forçar
    o outro modo no /confirm.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any
from uuid import UUID

import structlog

from app.core.crypto import mask_cpf
from app.models.scp import ParticipanteSCP, RegraCota
from app.services.beneficiario_service import BeneficiarioService
from app.services.importacao import _ler_planilha, _normalizar_chave
from app.validators.cpf import validar_cpf

log = structlog.get_logger()


class ScpImportError(Exception):
    """Erro de importação de participantes SCP."""


# Aliases de coluna (normalizados sem acento/espaço) → campo lógico.
_ALIASES_CPF = {
    "cpf",
    "documento",
    "doc",
    "cpfmedico",
    "cpfprestador",
    "cpfprofissional",
    "cpfsocio",
    "cpfparticipante",
    "numerocpf",
}
_ALIASES_NOME = {
    "nome",
    "nomemedico",
    "medico",
    "nomecompleto",
    "participante",
    "socio",
    "prestador",
    "profissional",
}
_ALIASES_PCT = {
    "percentual",
    "percentualmedico",
    "percentualrepasse",
    "percentualsocio",
    "percentualparticipacao",
    "participacao",
    "repasse",
    "repassemedico",
    "repasseempresa",
    "cota",
    "percent",
    "perc",
    "pct",
    "porcentagem",
    "%",
}

# ---- preview cache (mesmo padrão do beneficiario_service) ----
_PREVIEW_CACHE: dict[str, dict[str, Any]] = {}
_PREVIEW_TTL_SECS = 30 * 60


def _gc() -> None:
    agora = time.time()
    for t in [t for t, p in _PREVIEW_CACHE.items() if p["exp"] < agora]:
        _PREVIEW_CACHE.pop(t, None)


def _token(seed: bytes) -> str:
    return hashlib.sha256(seed + str(time.time()).encode()).hexdigest()[:32]


def _achar_coluna(colunas: list[str], aliases: set[str]) -> str | None:
    norm = {_normalizar_chave(c): c for c in colunas}
    for chave_norm, original in norm.items():
        if chave_norm in aliases:
            return original
    # match parcial (ex.: "percentualdomedico" contém "percentual")
    for chave_norm, original in norm.items():
        for a in aliases:
            if a and len(a) >= 4 and a in chave_norm:
                return original
    return None


def _parse_numero(valor: Any) -> tuple[float | None, bool]:
    """Converte célula em número. Retorna (numero, tinha_simbolo_percent)."""
    if valor is None:
        return None, False
    s = str(valor).strip()
    if not s:
        return None, False
    tinha_pct = "%" in s
    s = s.replace("%", "").strip()
    # decimal brasileiro: 1.234,56 → 1234.56 ; 8,5 → 8.5
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s), tinha_pct
    except ValueError:
        return None, tinha_pct


class ScpImportService:
    def __init__(self, db) -> None:  # type: ignore[no-untyped-def]
        self.db = db
        self.benef = BeneficiarioService(db)

    async def preview(
        self,
        *,
        cliente_id: UUID,
        conteudo: bytes,
        nome_arquivo: str,
        modo_forcado: str | None = None,
    ) -> dict[str, Any]:
        df = _ler_planilha(conteudo, nome_arquivo)
        if df.empty:
            raise ScpImportError("Planilha sem linhas.")

        colunas = list(df.columns)
        col_cpf = _achar_coluna(colunas, _ALIASES_CPF)
        col_nome = _achar_coluna(colunas, _ALIASES_NOME)
        col_pct = _achar_coluna(colunas, _ALIASES_PCT)

        faltando = [
            nome
            for nome, col in (("CPF", col_cpf), ("percentual", col_pct))
            if col is None
        ]
        if faltando:
            raise ScpImportError(
                f"Não encontrei a(s) coluna(s): {', '.join(faltando)}. "
                f"Colunas da planilha: {colunas}."
            )

        # 1ª passada: lê números crus pra detectar o modo (percentual x fração)
        numeros: list[float | None] = []
        algum_pct_simbolo = False
        for _, row in df.iterrows():
            n, tinha = _parse_numero(row.get(col_pct))
            numeros.append(n)
            algum_pct_simbolo = algum_pct_simbolo or tinha
        soma_crua = sum(n for n in numeros if n is not None)

        if modo_forcado in ("PERCENTUAL", "FRACAO"):
            modo = modo_forcado
        elif algum_pct_simbolo:
            modo = "PERCENTUAL"
        elif 0.5 <= soma_crua <= 1.5:
            modo = "FRACAO"
        else:
            modo = "PERCENTUAL"

        fator = 100.0 if modo == "FRACAO" else 1.0

        linhas: list[dict[str, Any]] = []
        cache: list[dict[str, Any]] = []
        qtd_ok = qtd_erro = 0
        soma_bp = 0

        for idx, row in df.iterrows():
            num_linha = int(idx) + 2  # +cabeçalho +base1
            erros: list[str] = []
            avisos: list[str] = []

            cpf_raw = str(row.get(col_cpf, "") or "")
            nome_raw = (
                str(row.get(col_nome, "") or "").strip() if col_nome else ""
            )
            pct_raw = str(row.get(col_pct, "") or "").strip()

            cpf_val = validar_cpf(cpf_raw)
            cpf_limpo = cpf_val.cpf_limpo or ""
            if not cpf_limpo or not cpf_val.is_valido:
                erros.append(f"CPF inválido: {cpf_val.mensagem or cpf_raw}")

            num, _ = _parse_numero(row.get(col_pct))
            percentual_pct: float | None = None
            percentual_bp = 0
            if num is None:
                erros.append(f"Percentual não numérico: '{pct_raw}'")
            else:
                percentual_pct = round(num * fator, 4)
                percentual_bp = round(percentual_pct * 100)
                if percentual_bp <= 0:
                    erros.append("Percentual zero ou negativo.")
                elif percentual_bp > 10000:
                    erros.append(
                        f"Percentual acima de 100% ({percentual_pct}%)."
                    )

            beneficiario_id: UUID | None = None
            ja_participante = False
            if cpf_limpo and not erros:
                exist = await self.benef.buscar_por_cpf(cliente_id, cpf_limpo)
                if exist is not None:
                    beneficiario_id = exist.id
                    part = await self._participante_existente(
                        cliente_id, exist.id
                    )
                    ja_participante = part is not None

            if erros:
                status = "ERRO"
                qtd_erro += 1
            else:
                status = "OK"
                qtd_ok += 1
                soma_bp += percentual_bp
                if beneficiario_id is None:
                    avisos.append("Médico não cadastrado — será criado (PENDENTE).")
                elif ja_participante:
                    avisos.append("Já é participante — o percentual será atualizado.")

            linhas.append(
                {
                    "linha_planilha": num_linha,
                    "nome": nome_raw or None,
                    "cpf_mascarado": mask_cpf(cpf_limpo) if cpf_limpo else None,
                    "percentual_original": pct_raw or None,
                    "percentual_pct": percentual_pct,
                    "percentual_bp": percentual_bp,
                    "status": status,
                    "ja_participante": ja_participante,
                    "erros": erros,
                    "avisos": avisos,
                }
            )
            cache.append(
                {
                    "status": status,
                    "cpf_limpo": cpf_limpo,
                    "nome": nome_raw,
                    "percentual_bp": percentual_bp,
                }
            )

        _gc()
        token = _token(conteudo[:128] + nome_arquivo.encode())
        _PREVIEW_CACHE[token] = {
            "cliente_id": str(cliente_id),
            "linhas": cache,
            "exp": time.time() + _PREVIEW_TTL_SECS,
        }

        return {
            "cliente_id": cliente_id,
            "coluna_cpf": col_cpf,
            "coluna_nome": col_nome,
            "coluna_percentual": col_pct,
            "modo_percentual": modo,
            "soma_percentual_bp": soma_bp,
            "soma_fecha_100": abs(soma_bp - 10000) <= 1,
            "total_linhas": len(linhas),
            "qtd_ok": qtd_ok,
            "qtd_erro": qtd_erro,
            "linhas": linhas,
            "token": token,
        }

    async def confirmar(self, *, token: str) -> dict[str, Any]:
        _gc()
        registro = _PREVIEW_CACHE.get(token)
        if registro is None:
            raise ScpImportError(
                "Token de importação inválido ou expirado. Reenvie a planilha."
            )
        cliente_id = UUID(registro["cliente_id"])

        criados = atualizados = ignorados = 0
        for linha in registro["linhas"]:
            if linha["status"] != "OK":
                ignorados += 1
                continue
            cpf_limpo = linha["cpf_limpo"]
            benef, _criado, _div = await self.benef.upsert_de_ficha(
                cliente_id,
                cpf_limpo=cpf_limpo,
                nome=linha["nome"],
                banco_codigo=None,
                agencia=None,
                conta=None,
                pix_tipo=None,
                pix_chave=None,
            )
            part = await self._participante_existente(cliente_id, benef.id)
            if part is not None:
                part.regra_cota = RegraCota.PERCENTUAL_FIXO
                part.percentual_bp = linha["percentual_bp"]
                part.ativo = True
                atualizados += 1
            else:
                self.db.add(
                    ParticipanteSCP(
                        cliente_id=cliente_id,
                        beneficiario_id=benef.id,
                        regra_cota=RegraCota.PERCENTUAL_FIXO,
                        percentual_bp=linha["percentual_bp"],
                    )
                )
                criados += 1

        await self.db.flush()
        _PREVIEW_CACHE.pop(token, None)
        log.info(
            "scp.import.confirmado",
            cliente_id=str(cliente_id),
            criados=criados,
            atualizados=atualizados,
            ignorados=ignorados,
        )
        return {
            "qtd_criados": criados,
            "qtd_atualizados": atualizados,
            "qtd_ignorados": ignorados,
        }

    async def _participante_existente(
        self, cliente_id: UUID, beneficiario_id: UUID
    ) -> ParticipanteSCP | None:
        from sqlalchemy import select

        q = await self.db.execute(
            select(ParticipanteSCP).where(
                ParticipanteSCP.cliente_id == cliente_id,
                ParticipanteSCP.beneficiario_id == beneficiario_id,
            )
        )
        return q.scalar_one_or_none()


__all__ = ["ScpImportService", "ScpImportError"]
