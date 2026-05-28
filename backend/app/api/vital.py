"""API do módulo MedPag Vital.

Endpoints montados em `/api/vital/*`.

Camadas de autenticação:
    1. INGESTÃO (sensores): header `X-Vital-Node-Token` — sem JWT,
       sem cookie, identifica o nó via api_key.
    2. GESTÃO (admin BPO/Coordenador): JWT normal via cookie/header.
    3. CONSULTA (operação): JWT normal.

PRIVACIDADE: ingestão obedece privacy_mode do nó (rejeita HR/BR brutos
quando ativado, retornando 403 com VITAL_PRIVACY_VIOLATION).
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_admin
from app.models.user import User
from app.models.vital import TipoAmbiente, TipoEvento, TipoSensor
from app.schemas.vital import (
    AmbienteCreate,
    AmbienteOut,
    AmbienteUpdate,
    AuditoriaResumo,
    EventoFiltro,
    EventoIngest,
    EventoIngestLote,
    EventoListResponse,
    EventoOut,
    IngestResult,
    NoComApiKey,
    NoCreate,
    NoOut,
    NoUpdate,
    VitalStats,
)
from app.services.vital_service import VitalService

router = APIRouter()


# ============================================================
# Ingestão (sensor → servidor)
# ============================================================


@router.post(
    "/eventos",
    response_model=IngestResult,
    status_code=202,
    summary="Sensor envia um evento (autenticação por X-Vital-Node-Token)",
)
async def ingerir_evento(
    payload: EventoIngest,
    x_vital_node_token: str = Header(..., description="API key do nó sensor"),
    db: AsyncSession = Depends(get_db),
) -> IngestResult:
    """Endpoint de ingestão individual — usado por sensores RuView/ESP32.

    Header obrigatório: `X-Vital-Node-Token: vital_<token>`
    """
    svc = VitalService(db)
    no = await svc.autenticar_no_por_api_key(x_vital_node_token)
    await svc.ingerir_evento(no=no, evento=payload)
    return IngestResult(aceitos=1)


@router.post(
    "/eventos/lote",
    response_model=IngestResult,
    status_code=202,
    summary="Sensor envia múltiplos eventos em batch (otimizado)",
)
async def ingerir_eventos_lote(
    payload: EventoIngestLote,
    x_vital_node_token: str = Header(..., description="API key do nó sensor"),
    db: AsyncSession = Depends(get_db),
) -> IngestResult:
    """Batch ingest — ESP32 acumula ~20 amostras (1s @ 20Hz) e envia."""
    svc = VitalService(db)
    no = await svc.autenticar_no_por_api_key(x_vital_node_token)
    return await svc.ingerir_lote(no=no, lote=payload)


# ============================================================
# Consulta de eventos (operação)
# ============================================================


@router.get(
    "/eventos",
    response_model=EventoListResponse,
    summary="Lista eventos com filtros (timeline / dashboard)",
)
async def listar_eventos(
    cliente_id: UUID | None = Query(default=None),
    ambiente_id: UUID | None = Query(default=None),
    no_id: UUID | None = Query(default=None),
    tipo: TipoEvento | None = Query(default=None),
    de: datetime | None = Query(default=None),
    ate: datetime | None = Query(default=None),
    data: date | None = Query(default=None),
    limite: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventoListResponse:
    """Timeline filtrável. Use combinações: cliente + ambiente + tipo."""
    svc = VitalService(db)
    filtro = EventoFiltro(
        cliente_id=cliente_id,
        ambiente_id=ambiente_id,
        no_id=no_id,
        tipo=tipo,
        de=de,
        ate=ate,
        data=data,
        limite=limite,
        offset=offset,
    )
    items, total = await svc.listar_eventos(filtro=filtro)
    return EventoListResponse(
        items=[EventoOut.model_validate(i) for i in items],
        total=total,
    )


# ============================================================
# Stats agregadas
# ============================================================


@router.get(
    "/stats",
    response_model=VitalStats,
    summary="Resumo executivo do módulo (dashboard inicial)",
)
async def stats(
    cliente_id: UUID = Query(...),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VitalStats:
    svc = VitalService(db)
    return await svc.stats_dashboard(cliente_id=cliente_id)


# ============================================================
# Ambientes (CRUD)
# ============================================================


@router.post(
    "/ambientes",
    response_model=AmbienteOut,
    status_code=201,
    summary="Cria um ambiente monitorado",
)
async def criar_ambiente(
    payload: AmbienteCreate,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AmbienteOut:
    svc = VitalService(db)
    amb = await svc.criar_ambiente(
        cliente_id=payload.cliente_id,
        nome=payload.nome,
        tipo=payload.tipo,
        descricao=payload.descricao,
        referencia_externa=payload.referencia_externa,
    )
    return AmbienteOut.model_validate(amb)


@router.get(
    "/ambientes",
    response_model=list[AmbienteOut],
    summary="Lista ambientes monitorados de um cliente",
)
async def listar_ambientes(
    cliente_id: UUID = Query(...),
    incluir_inativos: bool = Query(default=False),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AmbienteOut]:
    svc = VitalService(db)
    items = await svc.listar_ambientes(
        cliente_id=cliente_id, somente_ativos=not incluir_inativos
    )
    return [AmbienteOut.model_validate(i) for i in items]


@router.patch(
    "/ambientes/{ambiente_id}",
    response_model=AmbienteOut,
    summary="Atualiza um ambiente",
)
async def atualizar_ambiente(
    ambiente_id: UUID,
    payload: AmbienteUpdate,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AmbienteOut:
    svc = VitalService(db)
    campos = payload.model_dump(exclude_unset=True)
    amb = await svc.atualizar_ambiente(ambiente_id=ambiente_id, **campos)
    return AmbienteOut.model_validate(amb)


# ============================================================
# Nós (sensores)
# ============================================================


@router.post(
    "/nos",
    response_model=NoComApiKey,
    status_code=201,
    summary="Cadastra um sensor físico (devolve API key UMA vez)",
)
async def criar_no(
    payload: NoCreate,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> NoComApiKey:
    """Apenas ADMIN cria sensores. Devolve a `api_key` em texto puro
    uma única vez — guarde no provisionamento do ESP32.
    """
    svc = VitalService(db)
    no, api_key = await svc.criar_no(
        cliente_id=payload.cliente_id,
        node_id=payload.node_id,
        tipo=payload.tipo,
        apelido=payload.apelido,
        ambiente_id=payload.ambiente_id,
        privacy_mode=payload.privacy_mode,
    )
    base = NoOut.model_validate(no)
    return NoComApiKey(**base.model_dump(), api_key=api_key)


@router.get(
    "/nos",
    response_model=list[NoOut],
    summary="Lista sensores de um cliente",
)
async def listar_nos(
    cliente_id: UUID = Query(...),
    incluir_inativos: bool = Query(default=False),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NoOut]:
    svc = VitalService(db)
    items = await svc.listar_nos(
        cliente_id=cliente_id, somente_ativos=not incluir_inativos
    )
    return [NoOut.model_validate(i) for i in items]


@router.patch(
    "/nos/{no_id}",
    response_model=NoOut,
    summary="Atualiza configuração do nó (apelido, ambiente, privacy_mode)",
)
async def atualizar_no(
    no_id: UUID,
    payload: NoUpdate,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> NoOut:
    svc = VitalService(db)
    campos = payload.model_dump(exclude_unset=True)
    no = await svc.atualizar_no(no_id=no_id, **campos)
    return NoOut.model_validate(no)


@router.post(
    "/nos/{no_id}/rotacionar-key",
    response_model=NoComApiKey,
    summary="Rotaciona a API key do nó (em caso de comprometimento)",
)
async def rotacionar_api_key_no(
    no_id: UUID,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> NoComApiKey:
    svc = VitalService(db)
    no, api_key = await svc.regenerar_api_key(no_id=no_id)
    base = NoOut.model_validate(no)
    return NoComApiKey(**base.model_dump(), api_key=api_key)


# ============================================================
# Auditoria cruzada
# ============================================================


@router.get(
    "/auditoria/lancamento/{lancamento_id}",
    response_model=AuditoriaResumo,
    summary="Cruza um lançamento médico com eventos Vital do mesmo período",
)
async def auditar_lancamento(
    lancamento_id: UUID,
    ambiente_id: UUID | None = Query(default=None),
    inicio: datetime | None = Query(default=None),
    fim: datetime | None = Query(default=None),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuditoriaResumo:
    """Antifraude: para um lançamento de cirurgia/procedimento, verifica
    quais sinais Vital foram detectados no mesmo ambiente/período.

    Retorna veredito automático: VALIDO | AUDITORIA | INSUFICIENTE.
    """
    svc = VitalService(db)
    return await svc.auditar_lancamento(
        lancamento_id=lancamento_id,
        ambiente_id=ambiente_id,
        inicio=inicio,
        fim=fim,
    )


# ============================================================
# Metadados (enums pra dropdowns no front)
# ============================================================


@router.get(
    "/metadados/tipos-ambiente",
    summary="Lista tipos de ambiente disponíveis (dropdown)",
)
async def metadados_tipos_ambiente() -> list[dict[str, str]]:
    return [{"value": t.value, "label": t.value.replace("_", " ")} for t in TipoAmbiente]


@router.get(
    "/metadados/tipos-sensor",
    summary="Lista tipos de sensor disponíveis (dropdown)",
)
async def metadados_tipos_sensor() -> list[dict[str, str]]:
    return [{"value": t.value, "label": t.value.replace("_", " ")} for t in TipoSensor]


@router.get(
    "/metadados/tipos-evento",
    summary="Lista tipos de evento disponíveis (filtro)",
)
async def metadados_tipos_evento() -> list[dict[str, str]]:
    return [{"value": t.value, "label": t.value.replace("_", " ")} for t in TipoEvento]


__all__ = ["router"]
