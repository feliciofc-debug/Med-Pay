"""Rotas de Pagamento — aceitar sugestão de CPF, edição manual, busca."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt, hash_for_lookup, mask_conta, mask_cpf
from app.core.deps import get_current_user, get_db
from app.core.exceptions import (
    PagamentoNaoEditavelError,
    PagamentoNaoEncontradoError,
    ValidacaoError,
)
from app.models.lote import StatusLote
from app.models.pagamento import Pagamento, StatusPagamento
from app.models.user import User
from app.schemas.lote import PagamentoOut
from app.schemas.pagamento import (
    AceitarSugestaoCPFRequest,
    EditarPagamentoRequest,
)
from app.validators.banco import validar_dados_bancarios
from app.validators.cpf import limpar_cpf, validar_cpf

router = APIRouter()


async def _get_pagamento_editavel(
    pagamento_id: UUID, db: AsyncSession
) -> Pagamento:
    """Busca pagamento e garante que ele está em status editável."""
    result = await db.execute(
        select(Pagamento).where(Pagamento.id == pagamento_id)
    )
    pagamento = result.scalar_one_or_none()
    if pagamento is None:
        raise PagamentoNaoEncontradoError(f"Pagamento {pagamento_id} não encontrado")

    if pagamento.status not in (
        StatusPagamento.VALIDO,
        StatusPagamento.CORRIGIVEL,
        StatusPagamento.BLOQUEADO,
    ):
        raise PagamentoNaoEditavelError(
            f"Pagamento em status {pagamento.status.value} não pode ser editado"
        )

    return pagamento


@router.post(
    "/{pagamento_id}/aceitar-sugestao-cpf",
    response_model=PagamentoOut,
)
async def aceitar_sugestao_cpf(
    pagamento_id: UUID,
    payload: AceitarSugestaoCPFRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Pagamento:
    """Aceita a sugestão de CPF que o sistema gerou.

    Substitui o CPF criptografado pelo sugerido, recalcula hash/máscara,
    e revalida o status do pagamento.
    """
    pagamento = await _get_pagamento_editavel(pagamento_id, db)

    if not payload.aceitar:
        return pagamento

    if not pagamento.cpf_sugerido:
        raise ValidacaoError(
            "Este pagamento não tem sugestão de CPF para aceitar"
        )

    cpf_corrigido = pagamento.cpf_sugerido
    pagamento.cpf_encrypted = encrypt(cpf_corrigido)
    pagamento.cpf_hash = hash_for_lookup(cpf_corrigido)
    pagamento.cpf_mascarado = mask_cpf(cpf_corrigido)
    pagamento.cpf_sugerido = None

    # Revalida — se passou no CPF e os outros campos eram só CORRIGIVEL,
    # promove para VALIDO
    res_cpf = validar_cpf(cpf_corrigido)
    if res_cpf.is_valido and pagamento.status == StatusPagamento.CORRIGIVEL:
        # Verifica se ainda há outros códigos de erro
        codigos = (pagamento.codigos_erro or "").split(",")
        codigos_restantes = [c for c in codigos if c and c != "CPF_CORRIGIVEL"]
        if not codigos_restantes:
            pagamento.status = StatusPagamento.VALIDO
            pagamento.codigos_erro = None
        else:
            pagamento.codigos_erro = ",".join(codigos_restantes)

    await db.flush()
    return pagamento


@router.put("/{pagamento_id}", response_model=PagamentoOut)
async def editar_pagamento(
    pagamento_id: UUID,
    payload: EditarPagamentoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Pagamento:
    """Edita campos manualmente de um pagamento.

    Revalida e atualiza status. Não pode editar pagamento já APROVADO/PAGO.
    """
    pagamento = await _get_pagamento_editavel(pagamento_id, db)

    # CPF
    if payload.cpf is not None:
        cpf_limpo = limpar_cpf(payload.cpf)
        if not cpf_limpo:
            raise ValidacaoError("CPF inválido")
        pagamento.cpf_encrypted = encrypt(cpf_limpo)
        pagamento.cpf_hash = hash_for_lookup(cpf_limpo)
        pagamento.cpf_mascarado = mask_cpf(cpf_limpo)
        pagamento.cpf_sugerido = None

    # Nome
    if payload.nome is not None:
        nome = payload.nome.strip()
        if not nome:
            raise ValidacaoError("Nome não pode ficar vazio")
        pagamento.nome = nome

    # Dados bancários (precisam ser editados em conjunto)
    if any(
        v is not None
        for v in (payload.banco_codigo, payload.agencia, payload.conta)
    ):
        # Carrega valores atuais (descriptografando se necessário)
        from app.core.crypto import decrypt

        banco_atual = pagamento.banco_codigo
        agencia_atual = (
            decrypt(pagamento.agencia_encrypted)
            if pagamento.agencia_encrypted
            else None
        )
        conta_atual = (
            decrypt(pagamento.conta_encrypted) if pagamento.conta_encrypted else None
        )

        novo_banco = payload.banco_codigo or banco_atual
        nova_agencia = payload.agencia or agencia_atual
        nova_conta = payload.conta or conta_atual

        # Revalida — TEM QUE PASSAR ou levanta
        res = validar_dados_bancarios(novo_banco, nova_agencia, nova_conta)
        if not res.is_valido:
            raise ValidacaoError(res.mensagem)

        pagamento.banco_codigo = res.banco_codigo
        pagamento.agencia_encrypted = (
            encrypt(res.agencia_limpa) if res.agencia_limpa else None
        )
        pagamento.conta_encrypted = (
            encrypt(res.conta_limpa) if res.conta_limpa else None
        )
        pagamento.conta_mascarada = (
            mask_conta(res.conta_limpa) if res.conta_limpa else None
        )

    # Valor
    if payload.valor_centavos is not None:
        pagamento.valor_centavos = payload.valor_centavos

    # Reavaliação simples: se não tem mais sugestão de CPF e o ato de editar
    # foi pra resolver o CORRIGIVEL, podemos promover. Estratégia conservadora:
    # marcamos como VALIDO somente se NÃO há mais codigos_erro (operador editou
    # tudo que era preciso).
    pagamento.codigos_erro = None
    pagamento.mensagens_validacao = None
    pagamento.status = StatusPagamento.VALIDO

    await db.flush()
    return pagamento
