"""Rotas de bancos — lista FEBRABAN e validação de dados bancários.

Endpoints públicos para o frontend usar em autocomplete e validação
em tempo real (sem expor regras internas do CNAB).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.deps import get_current_user
from app.models.user import User
from app.validators.banco import (
    _BANCOS_SUPORTADOS,
    _FEBRABAN_TODOS,
    codigo_febraban_valido,
    nome_banco,
    obter_banco,
    validar_dados_bancarios,
)

router = APIRouter()


class BancoOut(BaseModel):
    codigo: str
    nome: str
    suportado_cnab: bool  # True se a Unicred (banco pagador) tem regra específica


class ValidarBancoRequest(BaseModel):
    banco: str | None = None
    agencia: str | None = None
    conta: str | None = None


class ValidarBancoResponse(BaseModel):
    valido: bool
    banco_codigo: str | None
    banco_nome: str | None
    agencia_limpa: str | None
    conta_limpa: str | None
    codigo_erro: str | None
    mensagem: str


@router.get("", response_model=list[BancoOut])
async def listar_bancos(
    _: User = Depends(get_current_user),
) -> list[BancoOut]:
    """Lista oficial FEBRABAN (códigos + nomes).

    Usado pelo frontend para:
    - Autocomplete na revisão da ficha
    - Mostrar nome do banco quando o usuário digita só o código
    - Validar em tempo real se o código existe
    """
    bancos: list[BancoOut] = []
    suportados = set(_BANCOS_SUPORTADOS.keys())
    todos = {**_FEBRABAN_TODOS}
    for codigo, regra in _BANCOS_SUPORTADOS.items():
        todos.setdefault(codigo, regra.nome)
    for codigo in sorted(todos.keys()):
        bancos.append(
            BancoOut(
                codigo=codigo,
                nome=todos[codigo],
                suportado_cnab=codigo in suportados,
            )
        )
    return bancos


@router.get("/{codigo}", response_model=BancoOut | None)
async def obter_banco_por_codigo(
    codigo: str,
    _: User = Depends(get_current_user),
) -> BancoOut | None:
    """Busca um banco pelo código FEBRABAN. Retorna None se não existir."""
    if not codigo_febraban_valido(codigo):
        return None
    nome = nome_banco(codigo) or ""
    regra = obter_banco(codigo)
    return BancoOut(
        codigo=codigo.zfill(3),
        nome=nome,
        suportado_cnab=regra is not None and regra.codigo in _BANCOS_SUPORTADOS,
    )


@router.post("/validar", response_model=ValidarBancoResponse)
async def validar_banco(
    payload: ValidarBancoRequest,
    _: User = Depends(get_current_user),
) -> ValidarBancoResponse:
    """Valida banco + agência + conta sem efeito colateral.

    Usado para feedback em tempo real na tela de revisão da ficha
    (antes de gerar o lote). Retorna mensagem em português pronta
    para mostrar ao usuário.
    """
    resultado = validar_dados_bancarios(
        payload.banco, payload.agencia, payload.conta
    )
    return ValidarBancoResponse(
        valido=resultado.is_valido,
        banco_codigo=resultado.banco_codigo,
        banco_nome=resultado.banco_nome,
        agencia_limpa=resultado.agencia_limpa,
        conta_limpa=resultado.conta_limpa,
        codigo_erro=resultado.codigo_erro,
        mensagem=resultado.mensagem,
    )


class ValidarPIXRequest(BaseModel):
    chave: str
    tipo: str | None = None
    cpf_titular: str | None = None


class ValidarPIXResponse(BaseModel):
    valida: bool
    tipo_detectado: str | None
    chave_normalizada: str | None
    codigo_erro: str | None
    mensagem: str


@router.post("/pix/validar", response_model=ValidarPIXResponse)
async def validar_pix(
    payload: ValidarPIXRequest,
    _: User = Depends(get_current_user),
) -> ValidarPIXResponse:
    """Valida sintaxe + titularidade local de uma chave PIX.

    Camada local (gratis): valida formato por tipo, auto-detecta o
    tipo quando nao informado, e compara com CPF do titular quando a
    chave for do tipo CPF. Camada DICT (paga) sera plugada depois.
    """
    from app.validators.pix import validar_chave_pix

    resultado = validar_chave_pix(
        payload.chave, tipo=payload.tipo, cpf_titular=payload.cpf_titular
    )
    return ValidarPIXResponse(
        valida=resultado.is_valida,
        tipo_detectado=(
            resultado.tipo_detectado.value if resultado.tipo_detectado else None
        ),
        chave_normalizada=resultado.chave_normalizada,
        codigo_erro=resultado.codigo_erro,
        mensagem=resultado.mensagem,
    )


__all__ = ["router"]
