"""Serviços do fluxo de autoatendimento do médico anestesista.

Auth leve por CRM:
    - O médico não tem User no sistema.
    - O backend gera um JWT especial (`type="anestesista"`) com claims
      `beneficiario_id`, `cliente_id` e `crm`.
    - Validade curta (default: 4h) — depois precisa re-entrar com o CRM.
    - Sem persistência de sessão server-side (stateless).

Privacidade:
    - Toda consulta de lançamento é filtrada por `beneficiario_id` do token.
    - Nunca exibe lançamentos de outros médicos.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import jwt
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    MedPagException,
    PermissaoNegadaError,
    TokenInvalidoError,
    ValidacaoError,
)
from app.core.security import JWTError, decode_token
from app.models.beneficiario import Beneficiario, StatusBeneficiario
from app.models.cliente import Cliente
from app.models.codigo_servico import CodigoServico
from app.models.lancamento_servico import LancamentoServico, StatusLancamento


# Duração do token leve por CRM. Curta porque é "kiosk-mode" — médico
# entra, lança, sai. Renova entrando com CRM de novo.
ANESTESISTA_TOKEN_EXPIRE_MINUTES = 240


class CrmAmbiguoError(MedPagException):
    """CRM existe em mais de um cliente — front precisa desambiguar."""

    code = "CRM_AMBIGUO"
    status_code = 409


class CrmNaoEncontradoError(MedPagException):
    """CRM não cadastrado em nenhum cliente."""

    code = "CRM_NAO_ENCONTRADO"
    status_code = 404


class CodigoServicoNaoEncontradoError(MedPagException):
    """Código de serviço inválido / inativo no cliente."""

    code = "CODIGO_SERVICO_NAO_ENCONTRADO"
    status_code = 404


class CodigoServicoDuplicadoError(MedPagException):
    """Tentativa de criar código que já existe naquele cliente."""

    code = "CODIGO_SERVICO_DUPLICADO"
    status_code = 409


class LancamentoNaoEncontradoError(MedPagException):
    code = "LANCAMENTO_NAO_ENCONTRADO"
    status_code = 404


# ============================================================
# Normalização de CRM
# ============================================================


def normalizar_crm(crm: str) -> str:
    """Padroniza CRM pra comparação: dígitos + barra + UF maiúscula.

    Aceita: "12345/SP", "12345 SP", "12345-sp", "CRM 12345/SP", " 12345 / sp "
    Sempre retorna: "12345/SP" (se houver UF) ou apenas os dígitos.
    """
    raw = crm.strip().upper().replace("CRM", "").strip()
    # extrai dígitos consecutivos
    digitos = "".join(c for c in raw if c.isdigit())
    if not digitos:
        raise ValidacaoError("CRM deve conter dígitos", code="CRM_INVALIDO")
    # extrai UF (2 letras alpha após os dígitos, se houver)
    sufixo = raw[len(raw) - 2 :] if len(raw) >= 2 else ""
    uf = sufixo if sufixo.isalpha() else ""
    return f"{digitos}/{uf}" if uf else digitos


# ============================================================
# Token leve por CRM
# ============================================================


def _gerar_token_anestesista(
    *, beneficiario_id: UUID, cliente_id: UUID, crm: str
) -> tuple[str, int]:
    """Gera JWT type=anestesista. Retorna (token, segundos_até_expirar)."""
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=ANESTESISTA_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(beneficiario_id),
        "cliente_id": str(cliente_id),
        "crm": crm,
        "iat": now,
        "exp": expire,
        "type": "anestesista",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, ANESTESISTA_TOKEN_EXPIRE_MINUTES * 60


def decode_token_anestesista(token: str) -> dict[str, Any]:
    """Decodifica token de anestesista. Levanta TokenInvalidoError se algo errado."""
    try:
        payload = decode_token(token)
    except JWTError as exc:
        raise TokenInvalidoError("Token de sessão inválido") from exc

    if payload.get("type") != "anestesista":
        raise TokenInvalidoError("Token não é de sessão de anestesista")

    if "sub" not in payload or "cliente_id" not in payload:
        raise TokenInvalidoError("Token incompleto")

    return payload


# ============================================================
# Service
# ============================================================


class AnestesistaService:
    """Operações do fluxo do médico anestesista."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -------- Auth --------

    async def login_por_crm(
        self,
        *,
        crm: str,
        cliente_id: UUID | None = None,
    ) -> tuple[Beneficiario, Cliente, str, int]:
        """Inicia sessão por CRM. Retorna (med, cliente, token, expires_in)."""
        crm_norm = normalizar_crm(crm)

        stmt = (
            select(Beneficiario, Cliente)
            .join(Cliente, Beneficiario.cliente_id == Cliente.id)
            .where(Beneficiario.crm == crm_norm)
            .where(Beneficiario.status == StatusBeneficiario.ATIVO)
        )
        if cliente_id is not None:
            stmt = stmt.where(Beneficiario.cliente_id == cliente_id)

        result = await self.db.execute(stmt)
        rows = result.all()

        if not rows:
            raise CrmNaoEncontradoError(
                f"CRM {crm_norm} não encontrado. Verifique se está cadastrado."
            )
        if len(rows) > 1:
            raise CrmAmbiguoError(
                "CRM cadastrado em mais de uma operação. Especifique o cliente."
            )

        beneficiario, cliente = rows[0]
        token, expires_in = _gerar_token_anestesista(
            beneficiario_id=beneficiario.id,
            cliente_id=beneficiario.cliente_id,
            crm=crm_norm,
        )
        return beneficiario, cliente, token, expires_in

    # -------- Códigos de serviço --------

    async def buscar_codigo(self, *, cliente_id: UUID, codigo: str) -> CodigoServico:
        """Busca código pelo identificador (case-insensitive)."""
        stmt = (
            select(CodigoServico)
            .where(CodigoServico.cliente_id == cliente_id)
            .where(func.upper(CodigoServico.codigo) == codigo.strip().upper())
            .where(CodigoServico.ativo.is_(True))
        )
        result = await self.db.execute(stmt)
        cod = result.scalar_one_or_none()
        if cod is None:
            raise CodigoServicoNaoEncontradoError(
                f"Código '{codigo}' não encontrado ou inativo nesta operação."
            )
        return cod

    async def listar_codigos(
        self, *, cliente_id: UUID, somente_ativos: bool = True
    ) -> list[CodigoServico]:
        """Lista todos os códigos do cliente (pra autocomplete)."""
        stmt = (
            select(CodigoServico)
            .where(CodigoServico.cliente_id == cliente_id)
            .order_by(CodigoServico.codigo.asc())
        )
        if somente_ativos:
            stmt = stmt.where(CodigoServico.ativo.is_(True))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def criar_codigo(
        self,
        *,
        cliente_id: UUID,
        codigo: str,
        descricao: str,
        valor_centavos: int,
        categoria: str | None = None,
        porte: str | None = None,
        observacoes: str | None = None,
    ) -> CodigoServico:
        """Admin: cria um código novo."""
        cod = CodigoServico(
            cliente_id=cliente_id,
            codigo=codigo.strip().upper(),
            descricao=descricao.strip(),
            valor_centavos=valor_centavos,
            categoria=categoria,
            porte=porte,
            observacoes=observacoes,
        )
        self.db.add(cod)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise CodigoServicoDuplicadoError(
                f"Código '{codigo}' já existe nesta operação."
            ) from exc
        await self.db.refresh(cod)
        return cod

    # -------- Lançamentos --------

    async def criar_lancamento(
        self,
        *,
        beneficiario_id: UUID,
        cliente_id: UUID,
        codigo: str,
        data_servico: Any,
        hospital_local: str | None = None,
        paciente_iniciais: str | None = None,
        observacoes: str | None = None,
    ) -> LancamentoServico:
        """Médico cria lançamento. Snapshot do código é tirado agora."""
        cod = await self.buscar_codigo(cliente_id=cliente_id, codigo=codigo)

        lanc = LancamentoServico(
            cliente_id=cliente_id,
            beneficiario_id=beneficiario_id,
            codigo_servico_id=cod.id,
            data_servico=data_servico,
            codigo_snapshot=cod.codigo,
            descricao_snapshot=cod.descricao,
            valor_centavos=cod.valor_centavos,
            hospital_local=hospital_local,
            paciente_iniciais=(
                paciente_iniciais.strip().upper() if paciente_iniciais else None
            ),
            observacoes=observacoes,
            status=StatusLancamento.LANCADO,
        )
        self.db.add(lanc)
        await self.db.flush()
        await self.db.refresh(lanc)
        return lanc

    async def listar_meus_lancamentos(
        self,
        *,
        beneficiario_id: UUID,
        cliente_id: UUID,
        limit: int = 100,
    ) -> tuple[list[LancamentoServico], int, int]:
        """Lista lançamentos do médico. Filtro hard por beneficiario_id.

        Retorna (itens, total, soma_valores_centavos).
        """
        # Aplica filtro de privacidade — NUNCA mostra lançamentos de outros.
        base = (
            select(LancamentoServico)
            .where(LancamentoServico.beneficiario_id == beneficiario_id)
            .where(LancamentoServico.cliente_id == cliente_id)
            .where(LancamentoServico.status != StatusLancamento.CANCELADO)
        )
        result = await self.db.execute(
            base.order_by(LancamentoServico.data_servico.desc()).limit(limit)
        )
        items = list(result.scalars().all())

        total = len(items)
        total_centavos = sum(it.valor_centavos for it in items)
        return items, total, total_centavos

    async def cancelar_lancamento(
        self,
        *,
        lancamento_id: UUID,
        beneficiario_id: UUID,
    ) -> LancamentoServico:
        """Cancela um lançamento — somente o próprio médico, e só se LANCADO."""
        stmt = select(LancamentoServico).where(LancamentoServico.id == lancamento_id)
        result = await self.db.execute(stmt)
        lanc = result.scalar_one_or_none()
        if lanc is None:
            raise LancamentoNaoEncontradoError("Lançamento não encontrado.")
        if lanc.beneficiario_id != beneficiario_id:
            # privacidade hard — nem informa que existe
            raise PermissaoNegadaError(
                "Você só pode cancelar seus próprios lançamentos."
            )
        if lanc.status != StatusLancamento.LANCADO:
            raise PermissaoNegadaError(
                "Este lançamento já foi conferido pelo BPO e não pode mais "
                "ser cancelado por você. Fale com o financeiro."
            )
        lanc.status = StatusLancamento.CANCELADO
        await self.db.flush()
        await self.db.refresh(lanc)
        return lanc


__all__ = [
    "AnestesistaService",
    "CodigoServicoDuplicadoError",
    "CodigoServicoNaoEncontradoError",
    "CrmAmbiguoError",
    "CrmNaoEncontradoError",
    "LancamentoNaoEncontradoError",
    "decode_token_anestesista",
    "normalizar_crm",
]
