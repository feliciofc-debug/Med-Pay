"""Rotas de gestão de planos e features por cliente.

Endpoints públicos (lista de planos pro signup):
    GET  /api/planos/publicos
    GET  /api/planos/features-catalogo

Endpoints admin (gestão por cliente):
    GET  /api/planos                              → lista todos planos
    GET  /api/planos/clientes/{id}                → estado assinatura cliente
    PUT  /api/planos/clientes/{id}/plano          → trocar plano
    PUT  /api/planos/clientes/{id}/features       → atualizar overrides
    PUT  /api/planos/clientes/{id}/status         → mudar status assinatura

Filosofia: rotas admin retornam o dict de `features_efetivas` já
resolvido — frontend não precisa replicar a lógica de override.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.deps import get_db, require_admin
from app.core.exceptions import (
    ClienteNaoEncontradoError,
    PlanoNaoEncontradoError,
    ValidacaoError,
)
from app.models.cliente import Cliente
from app.models.plano import Plano, StatusAssinatura
from app.models.user import User
from app.schemas.plano import (
    AtualizarFeaturesOverrideRequest,
    AtualizarPlanoClienteRequest,
    AtualizarStatusAssinaturaRequest,
    ClienteAssinaturaOut,
    FeatureDefOut,
    PlanoOut,
    PlanoResumoOut,
)
from app.services.feature_flags import (
    FEATURES_DISPONIVEIS,
    chaves_validas,
    features_resolvidas,
)

router = APIRouter()


# ============================================================
# Catálogo + planos (público / semi-público)
# ============================================================


@router.get("/features-catalogo", response_model=list[FeatureDefOut])
async def listar_features_catalogo() -> list[FeatureDefOut]:
    """Catálogo único de features disponíveis na plataforma.

    Frontend usa pra renderizar a tela de configuração de overrides
    (com nome amigável, descrição, categoria).
    """
    return [
        FeatureDefOut(
            chave=f.chave,
            nome=f.nome,
            descricao=f.descricao,
            categoria=f.categoria.value,
            tipo=f.tipo,
            default=f.default,
        )
        for f in FEATURES_DISPONIVEIS
    ]


@router.get("/publicos", response_model=list[PlanoOut])
async def listar_planos_publicos(
    db: AsyncSession = Depends(get_db),
) -> list[PlanoOut]:
    """Planos visíveis no signup self-service. Sem auth."""
    result = await db.execute(
        select(Plano)
        .where(Plano.publico.is_(True), Plano.ativo.is_(True))
        .order_by(Plano.ordem, Plano.preco_mensal_centavos)
    )
    return [PlanoOut.model_validate(p) for p in result.scalars().all()]


@router.get("", response_model=list[PlanoOut])
async def listar_todos_planos(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[PlanoOut]:
    """Todos os planos (públicos + contratuais). Só admin."""
    result = await db.execute(
        select(Plano).where(Plano.ativo.is_(True)).order_by(Plano.ordem)
    )
    return [PlanoOut.model_validate(p) for p in result.scalars().all()]


# ============================================================
# Estado de assinatura por cliente
# ============================================================


async def _carregar_cliente(db: AsyncSession, cliente_id: UUID) -> Cliente:
    result = await db.execute(
        select(Cliente)
        .where(Cliente.id == cliente_id, Cliente.deleted_at.is_(None))
        .options(joinedload(Cliente.plano))
    )
    cliente = result.scalar_one_or_none()
    if cliente is None:
        raise ClienteNaoEncontradoError(f"Cliente {cliente_id} não encontrado")
    return cliente


def _montar_assinatura_out(cliente: Cliente) -> ClienteAssinaturaOut:
    """Monta o DTO completo com features resolvidas."""
    return ClienteAssinaturaOut(
        id=cliente.id,
        nome=cliente.nome,
        cnpj=cliente.cnpj,
        status_assinatura=cliente.status_assinatura,
        trial_termina_em=cliente.trial_termina_em,
        plano=(
            PlanoResumoOut.model_validate(cliente.plano)
            if cliente.plano is not None
            else None
        ),
        features_override=cliente.features_override or {},
        features_efetivas=features_resolvidas(cliente),
    )


@router.get(
    "/clientes/{cliente_id}", response_model=ClienteAssinaturaOut
)
async def obter_assinatura_cliente(
    cliente_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ClienteAssinaturaOut:
    """Estado completo da assinatura + features efetivas do cliente."""
    cliente = await _carregar_cliente(db, cliente_id)
    return _montar_assinatura_out(cliente)


@router.put(
    "/clientes/{cliente_id}/plano", response_model=ClienteAssinaturaOut
)
async def trocar_plano_cliente(
    cliente_id: UUID,
    payload: AtualizarPlanoClienteRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ClienteAssinaturaOut:
    """Troca o plano do cliente.

    Se `iniciar_trial=True` e o plano novo tem `trial_dias > 0`:
        status → TRIAL
        trial_termina_em → agora + trial_dias
    Caso contrário:
        status → ATIVO
        trial_termina_em → null
    """
    cliente = await _carregar_cliente(db, cliente_id)

    novo_plano: Plano | None = None
    if payload.plano_id is not None:
        result = await db.execute(
            select(Plano).where(Plano.id == payload.plano_id, Plano.ativo.is_(True))
        )
        novo_plano = result.scalar_one_or_none()
        if novo_plano is None:
            raise PlanoNaoEncontradoError(
                f"Plano {payload.plano_id} não encontrado ou inativo"
            )

    cliente.plano_id = novo_plano.id if novo_plano else None

    if payload.iniciar_trial and novo_plano and novo_plano.trial_dias > 0:
        cliente.status_assinatura = StatusAssinatura.TRIAL
        cliente.trial_termina_em = datetime.now(UTC) + timedelta(
            days=novo_plano.trial_dias
        )
    else:
        cliente.status_assinatura = StatusAssinatura.ATIVO
        cliente.trial_termina_em = None

    await db.flush()
    await db.refresh(cliente, attribute_names=["plano"])
    return _montar_assinatura_out(cliente)


@router.put(
    "/clientes/{cliente_id}/features", response_model=ClienteAssinaturaOut
)
async def atualizar_features_cliente(
    cliente_id: UUID,
    payload: AtualizarFeaturesOverrideRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ClienteAssinaturaOut:
    """Atualiza o dict de overrides do cliente.

    Substitui o JSON inteiro (não faz merge). Cliente que quiser
    "voltar ao padrão do plano" manda `{}`.

    Valida que todas as chaves estão no catálogo.
    """
    cliente = await _carregar_cliente(db, cliente_id)

    catalogo = chaves_validas()
    invalidas = set(payload.features_override.keys()) - catalogo
    if invalidas:
        raise ValidacaoError(
            f"Chaves de feature inválidas: {', '.join(sorted(invalidas))}. "
            f"Veja /api/planos/features-catalogo para a lista válida."
        )

    cliente.features_override = payload.features_override
    await db.flush()
    return _montar_assinatura_out(cliente)


@router.put(
    "/clientes/{cliente_id}/status", response_model=ClienteAssinaturaOut
)
async def atualizar_status_assinatura(
    cliente_id: UUID,
    payload: AtualizarStatusAssinaturaRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ClienteAssinaturaOut:
    """Mudança manual de status (cancelar, reativar, marcar inadimplente).

    Útil enquanto não tem cobrança automática integrada — admin
    consegue corrigir estado manualmente.
    """
    cliente = await _carregar_cliente(db, cliente_id)
    cliente.status_assinatura = payload.status_assinatura
    if payload.trial_termina_em is not None or payload.status_assinatura != StatusAssinatura.TRIAL:
        cliente.trial_termina_em = payload.trial_termina_em
    await db.flush()
    return _montar_assinatura_out(cliente)
