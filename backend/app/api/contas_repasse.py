"""Contas de Repasse — gestão multi-conta por tenant.

Um tenant (ex.: a Atom) cadastra N contas, uma por banco (Bradesco, Itaú,
Unicred, Santander...). Cada hospital da carteira aponta pra uma delas.

Convive com o endpoint legado `/api/admin/empresa-pagadora` (singleton):
aquele edita a conta global (cliente_id NULL); este lida com as contas
próprias do tenant.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt, mask_conta
from app.core.deps import get_current_user, get_db, require_execucao_pagamento
from app.core.exceptions import LoteNaoEncontradoError, ValidacaoError
from app.models.empresa_config import EmpresaConfig, TipoInscricao
from app.models.user import User, UserRole
from app.schemas.conta_repasse import ContaRepasseOut, ContaRepasseRequest

router = APIRouter(prefix="/api/contas-repasse", tags=["contas-repasse"])
log = structlog.get_logger()


def _so_digitos(texto: str) -> str:
    return "".join(c for c in texto if c.isdigit())


def _owner_id(user: User, payload_cliente_id):
    """De quem é a conta. Admin interno pode mirar outro tenant (ou global);
    qualquer outro perfil cria sempre pra si."""
    if user.role == UserRole.ADMIN:
        return payload_cliente_id
    return user.cliente_id


def _aplica_campos(empresa: EmpresaConfig, payload: ContaRepasseRequest) -> None:
    cnpj_limpo = _so_digitos(payload.cnpj_cpf)
    if payload.tipo_inscricao == TipoInscricao.CNPJ and len(cnpj_limpo) != 14:
        raise ValidacaoError(f"CNPJ inválido: esperado 14 dígitos, recebido {len(cnpj_limpo)}")
    if payload.tipo_inscricao == TipoInscricao.CPF and len(cnpj_limpo) != 11:
        raise ValidacaoError(f"CPF inválido: esperado 11 dígitos, recebido {len(cnpj_limpo)}")

    cep_limpo = _so_digitos(payload.endereco_cep)
    if len(cep_limpo) != 8:
        raise ValidacaoError(f"CEP inválido: esperado 8 dígitos, recebido {len(cep_limpo)}")

    conta_limpa = "".join(c for c in payload.conta.upper() if c.isdigit() or c == "X")
    if not conta_limpa:
        raise ValidacaoError("Conta não pode ser vazia")

    empresa.apelido = (payload.apelido or "").strip() or None
    empresa.modo_execucao = payload.modo_execucao
    empresa.razao_social = payload.razao_social.strip()
    empresa.nome_fantasia = payload.nome_fantasia or None
    empresa.tipo_inscricao = payload.tipo_inscricao
    empresa.cnpj_cpf = cnpj_limpo
    empresa.banco_emissor = payload.banco_emissor
    empresa.banco_codigo = payload.banco_codigo
    empresa.agencia = payload.agencia
    empresa.agencia_dv = payload.agencia_dv
    empresa.conta_encrypted = encrypt(conta_limpa)
    empresa.conta_dv = payload.conta_dv
    empresa.conta_mascarada = mask_conta(conta_limpa)
    empresa.codigo_convenio = payload.codigo_convenio
    empresa.endereco_logradouro = payload.endereco_logradouro
    empresa.endereco_numero = payload.endereco_numero
    empresa.endereco_complemento = payload.endereco_complemento or None
    empresa.endereco_cidade = payload.endereco_cidade
    empresa.endereco_cep = cep_limpo
    empresa.endereco_uf = payload.endereco_uf.upper()
    if payload.proximo_numero_sequencial >= empresa.proximo_numero_sequencial:
        empresa.proximo_numero_sequencial = payload.proximo_numero_sequencial


@router.get("", response_model=list[ContaRepasseOut])
async def listar_contas(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EmpresaConfig]:
    """Lista as contas do tenant. Admin interno vê todas (inclui a global)."""
    stmt = select(EmpresaConfig).order_by(EmpresaConfig.created_at)
    if current_user.role != UserRole.ADMIN:
        stmt = stmt.where(EmpresaConfig.cliente_id == current_user.cliente_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=ContaRepasseOut, status_code=201)
async def criar_conta(
    payload: ContaRepasseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_execucao_pagamento),
) -> EmpresaConfig:
    """Cadastra uma nova conta de repasse pro tenant."""
    empresa = EmpresaConfig(ativo=True, proximo_numero_sequencial=1)
    empresa.cliente_id = _owner_id(current_user, payload.cliente_id)
    _aplica_campos(empresa, payload)
    db.add(empresa)
    await db.flush()
    await db.refresh(empresa)
    log.info("conta_repasse.criada", conta_id=str(empresa.id), cliente_id=str(empresa.cliente_id))
    return empresa


@router.put("/{conta_id}", response_model=ContaRepasseOut)
async def atualizar_conta(
    conta_id: str,
    payload: ContaRepasseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_execucao_pagamento),
) -> EmpresaConfig:
    """Atualiza uma conta de repasse existente do tenant."""
    empresa = await db.get(EmpresaConfig, conta_id)
    if empresa is None or (
        current_user.role != UserRole.ADMIN
        and empresa.cliente_id != current_user.cliente_id
    ):
        raise LoteNaoEncontradoError("Conta de repasse não encontrada")
    _aplica_campos(empresa, payload)
    await db.flush()
    await db.refresh(empresa)
    log.info("conta_repasse.atualizada", conta_id=str(empresa.id))
    return empresa


@router.post("/{conta_id}/desativar", response_model=ContaRepasseOut)
async def desativar_conta(
    conta_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_execucao_pagamento),
) -> EmpresaConfig:
    """Desativa uma conta (soft) — some das opções sem perder histórico."""
    empresa = await db.get(EmpresaConfig, conta_id)
    if empresa is None or (
        current_user.role != UserRole.ADMIN
        and empresa.cliente_id != current_user.cliente_id
    ):
        raise LoteNaoEncontradoError("Conta de repasse não encontrada")
    empresa.ativo = False
    await db.flush()
    await db.refresh(empresa)
    log.info("conta_repasse.desativada", conta_id=str(empresa.id))
    return empresa


__all__ = ["router"]
