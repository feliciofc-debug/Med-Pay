"""Carteira de hospitais — empresa de repasse (pai) administra seus hospitais.

A Atom (tenant MEDPAG_REPASSE/EMPRESA_REPASSE) cadastra aqui os hospitais
que atende. Cada hospital é um Cliente "filho" (cliente_pai_id = Atom),
ligado a uma Conta de Repasse (de qual conta sai o pagamento dele) e,
opcionalmente, com login próprio (o hospital sobe planilha / manda fichas
e acompanha os repasses; a Atom "entra no hospital" pra aprovar e pagar).

Isolamento: a Atom só enxerga/edita os próprios filhos (via
`verificar_acesso_cliente`, que já entende a relação pai→filho).
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    get_current_user,
    get_db,
    require_execucao_pagamento,
    verificar_acesso_cliente,
)
from app.core.exceptions import PermissaoNegadaError, ValidacaoError
from app.models.cliente import Cliente, ModoPagamento, TipoCliente
from app.models.empresa_config import EmpresaConfig
from app.models.user import User, UserRole
from app.services.auth import AuthService
from app.services.presets_negocio import get_preset

router = APIRouter(prefix="/api/carteira", tags=["carteira"])
log = structlog.get_logger()


# ============================================================
# Schemas
# ============================================================


class HospitalCarteiraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    cnpj: str | None
    modo_pagamento: ModoPagamento
    conta_pagadora_id: UUID | None
    conta_apelido: str | None = None
    ativo: bool
    tem_login: bool = False


class CriarHospitalRequest(BaseModel):
    nome: str = Field(min_length=2, max_length=255)
    cnpj: str | None = Field(default=None, max_length=18)
    modo_pagamento: ModoPagamento = ModoPagamento.CNAB_BANCARIO
    conta_pagadora_id: UUID | None = None
    # Pai explícito só pra admin interno cadastrar em nome de um tenant.
    cliente_pai_id: UUID | None = None
    # Login opcional do hospital (sobe planilha / vê repasses).
    login_email: str | None = None
    login_senha: str | None = None
    login_nome: str | None = None


class AtualizarHospitalRequest(BaseModel):
    nome: str | None = Field(default=None, max_length=255)
    cnpj: str | None = Field(default=None, max_length=18)
    modo_pagamento: ModoPagamento | None = None
    conta_pagadora_id: UUID | None = None
    ativo: bool | None = None


# ============================================================
# Helpers
# ============================================================


async def _resolver_pai(user: User, pai_id_payload: UUID | None) -> UUID:
    """Quem é o tenant pai da carteira nesta operação."""
    if user.cliente_id is not None:
        return user.cliente_id
    if pai_id_payload is not None:
        return pai_id_payload
    raise ValidacaoError(
        "Admin interno precisa informar 'cliente_pai_id' (de qual empresa "
        "de repasse é a carteira)."
    )


async def _validar_conta(
    db: AsyncSession, conta_id: UUID | None, pai_id: UUID
) -> None:
    if conta_id is None:
        return
    conta = await db.get(EmpresaConfig, conta_id)
    if conta is None:
        raise ValidacaoError("Conta de repasse não encontrada.")
    # A conta tem que ser do próprio pai (ou legada/global).
    if conta.cliente_id is not None and conta.cliente_id != pai_id:
        raise PermissaoNegadaError("Essa conta de repasse é de outro tenant.")


async def _serializar(
    db: AsyncSession, hospital: Cliente
) -> HospitalCarteiraOut:
    apelido = None
    if hospital.conta_pagadora_id is not None:
        conta = await db.get(EmpresaConfig, hospital.conta_pagadora_id)
        apelido = conta.apelido or (conta.razao_social if conta else None)
    tem_login = (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(User.cliente_id == hospital.id)
        )
    ).scalar_one() > 0
    return HospitalCarteiraOut(
        id=hospital.id,
        nome=hospital.nome,
        cnpj=hospital.cnpj,
        modo_pagamento=hospital.modo_pagamento,
        conta_pagadora_id=hospital.conta_pagadora_id,
        conta_apelido=apelido,
        ativo=hospital.ativo,
        tem_login=tem_login,
    )


# ============================================================
# Endpoints
# ============================================================


@router.get("/hospitais", response_model=list[HospitalCarteiraOut])
async def listar_hospitais(
    pai_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[HospitalCarteiraOut]:
    """Lista os hospitais-filhos do tenant (a carteira da empresa de repasse)."""
    alvo_pai = current_user.cliente_id or pai_id
    stmt = select(Cliente)
    if alvo_pai is not None:
        # Carteira de um tenant específico.
        stmt = stmt.where(Cliente.cliente_pai_id == alvo_pai)
    else:
        # Admin interno sem filtro: todos os hospitais que são filhos.
        stmt = stmt.where(Cliente.cliente_pai_id.isnot(None))
    stmt = stmt.order_by(Cliente.nome)
    result = await db.execute(stmt)
    return [await _serializar(db, h) for h in result.scalars().all()]


@router.post("/hospitais", response_model=HospitalCarteiraOut, status_code=201)
async def criar_hospital(
    payload: CriarHospitalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_execucao_pagamento),
) -> HospitalCarteiraOut:
    """Cadastra um hospital na carteira (Cliente filho + login opcional)."""
    pai_id = await _resolver_pai(current_user, payload.cliente_pai_id)
    await _validar_conta(db, payload.conta_pagadora_id, pai_id)

    preset = get_preset(TipoCliente.HOSPITAL)
    hospital = Cliente(
        nome=payload.nome.strip(),
        cnpj=(payload.cnpj or "").strip() or None,
        tipo=TipoCliente.HOSPITAL,
        modo_pagamento=payload.modo_pagamento,
        cliente_pai_id=pai_id,
        conta_pagadora_id=payload.conta_pagadora_id,
        features_override=dict(preset.features),
        ativo=True,
    )
    db.add(hospital)
    await db.flush()

    # Login opcional do hospital (role GESTOR, mas sem pagamento.execucao —
    # o hospital sobe planilha e vê repasses; quem executa é a Atom).
    if payload.login_email and payload.login_senha:
        email = payload.login_email.lower().strip()
        existente = await db.execute(select(User).where(User.email == email))
        if existente.scalar_one_or_none() is not None:
            raise ValidacaoError(f"Já existe um login com o e-mail {email}.")
        service = AuthService(db)
        novo = await service.criar_usuario(
            email=email,
            nome=(payload.login_nome or payload.nome).strip(),
            senha=payload.login_senha,
            role=UserRole.GESTOR,
        )
        novo.cliente_id = hospital.id

    await db.flush()
    await db.refresh(hospital)
    log.info(
        "carteira.hospital_criado",
        hospital_id=str(hospital.id),
        pai_id=str(pai_id),
        com_login=bool(payload.login_email),
    )
    return await _serializar(db, hospital)


@router.put("/hospitais/{hospital_id}", response_model=HospitalCarteiraOut)
async def atualizar_hospital(
    hospital_id: UUID,
    payload: AtualizarHospitalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_execucao_pagamento),
) -> HospitalCarteiraOut:
    """Atualiza um hospital da carteira (nome, conta ligada, modo, ativo)."""
    await verificar_acesso_cliente(
        db, current_user, hospital_id, mensagem="Hospital não é da sua carteira."
    )
    hospital = await db.get(Cliente, hospital_id)
    if hospital is None or hospital.cliente_pai_id is None:
        raise ValidacaoError("Hospital de carteira não encontrado.")

    if payload.conta_pagadora_id is not None:
        await _validar_conta(db, payload.conta_pagadora_id, hospital.cliente_pai_id)
        hospital.conta_pagadora_id = payload.conta_pagadora_id
    if payload.nome is not None:
        hospital.nome = payload.nome.strip()
    if payload.cnpj is not None:
        hospital.cnpj = payload.cnpj.strip() or None
    if payload.modo_pagamento is not None:
        hospital.modo_pagamento = payload.modo_pagamento
    if payload.ativo is not None:
        hospital.ativo = payload.ativo

    await db.flush()
    await db.refresh(hospital)
    log.info("carteira.hospital_atualizado", hospital_id=str(hospital.id))
    return await _serializar(db, hospital)


__all__ = ["router"]
