"""Schemas Pydantic do módulo MedPag Vital.

Cobre 3 superfícies:
    1. Ingestão pelo sensor (POST /api/vital/eventos com header X-Vital-Node-Token)
    2. Gestão admin (CRUD de ambientes e nós)
    3. Consulta (timeline, dashboard, auditoria cruzada com lançamentos)
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.vital import (
    StatusNo,
    TipoAmbiente,
    TipoEvento,
    TipoSensor,
)


# ============================================================
# Ambientes (CRUD admin)
# ============================================================


class AmbienteCreate(BaseModel):
    """Cria um ambiente monitorado."""

    cliente_id: UUID
    nome: str = Field(min_length=1, max_length=255)
    tipo: TipoAmbiente = TipoAmbiente.OUTRO
    descricao: str | None = Field(default=None, max_length=1024)
    referencia_externa: str | None = Field(default=None, max_length=120)


class AmbienteUpdate(BaseModel):
    """Atualiza um ambiente (todos os campos opcionais)."""

    nome: str | None = Field(default=None, min_length=1, max_length=255)
    tipo: TipoAmbiente | None = None
    descricao: str | None = Field(default=None, max_length=1024)
    referencia_externa: str | None = Field(default=None, max_length=120)
    ativo: bool | None = None


class AmbienteOut(BaseModel):
    """Visão do ambiente."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cliente_id: UUID
    nome: str
    tipo: TipoAmbiente
    descricao: str | None
    referencia_externa: str | None
    ativo: bool
    created_at: datetime


# ============================================================
# Nós (sensores físicos)
# ============================================================


class NoCreate(BaseModel):
    """Cadastra um sensor físico (gera api_key automaticamente)."""

    cliente_id: UUID
    node_id: str = Field(
        min_length=1, max_length=120,
        description="ID lógico que o firmware do sensor envia (ex: 'esp32-001').",
    )
    tipo: TipoSensor = TipoSensor.RUVIEW_ESP32_S3
    apelido: str | None = Field(default=None, max_length=255)
    ambiente_id: UUID | None = None
    privacy_mode: bool = False


class NoUpdate(BaseModel):
    """Atualiza configuração do nó."""

    apelido: str | None = Field(default=None, max_length=255)
    ambiente_id: UUID | None = None
    privacy_mode: bool | None = None
    ativo: bool | None = None
    tipo: TipoSensor | None = None


class NoOut(BaseModel):
    """Visão do nó sem expor a api_key (a key vai só no momento da criação)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cliente_id: UUID
    ambiente_id: UUID | None
    node_id: str
    tipo: TipoSensor
    apelido: str | None
    status: StatusNo
    privacy_mode: bool
    firmware_version: str | None
    last_seen_at: datetime | None
    last_rssi: float | None
    ativo: bool
    created_at: datetime


class NoComApiKey(NoOut):
    """Resposta única do POST /vital/nos — devolve api_key UMA vez."""

    api_key: str = Field(
        description=(
            "Token que o sensor deve enviar no header X-Vital-Node-Token. "
            "GUARDE BEM — não é exibido novamente."
        )
    )


# ============================================================
# Ingestão de eventos (autenticação por api_key do nó)
# ============================================================


class EventoIngest(BaseModel):
    """Payload enviado por um nó sensor a cada evento.

    O nó manda no header `X-Vital-Node-Token` o api_key dele, e o body
    é apenas o evento — não precisa identificar o cliente_id ou ambiente_id,
    porque a gente resolve a partir do api_key (= contexto do nó).
    """

    tipo: TipoEvento
    valor_num: float | None = None
    valor_texto: str | None = Field(default=None, max_length=255)
    confianca: float | None = Field(default=None, ge=0.0, le=1.0)
    observado_em: datetime | None = Field(
        default=None,
        description="Timestamp do sensor. Se None, usa NOW() do servidor.",
    )
    extras_json: str | None = Field(default=None, max_length=2048)
    firmware_version: str | None = Field(default=None, max_length=40)
    rssi: float | None = None


class EventoIngestLote(BaseModel):
    """Permite o sensor enviar um batch de eventos (mais eficiente em UDP/HTTP).

    Útil pra o ESP32 acumular ~20 amostras (1 segundo a 20Hz) e mandar de uma vez.
    """

    eventos: list[EventoIngest] = Field(min_length=1, max_length=200)
    firmware_version: str | None = Field(default=None, max_length=40)
    rssi: float | None = None


class IngestResult(BaseModel):
    """Confirmação simples pro sensor saber que o evento foi gravado."""

    aceitos: int
    rejeitados: int = 0
    erros: list[str] = Field(default_factory=list)


# ============================================================
# Consulta de eventos (dashboard / timeline)
# ============================================================


class EventoOut(BaseModel):
    """Evento individual (resposta de listagem)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cliente_id: UUID
    ambiente_id: UUID | None
    no_id: UUID | None
    tipo: TipoEvento
    valor_num: float | None
    valor_texto: str | None
    confianca: float | None
    observado_em: datetime
    created_at: datetime


class EventoListResponse(BaseModel):
    """Lista paginada de eventos."""

    items: list[EventoOut]
    total: int


# ============================================================
# Auditoria de Lançamento (cruzamento médico × Vital)
# ============================================================


class AuditoriaResumo(BaseModel):
    """Resumo cruzado de um lançamento médico com dados Vital.

    Mostra: "Dr. X lançou cirurgia 14h-15h30 sala 3 → o ambiente
    teve N pessoas, paciente deitado estável das 14h08 às 15h22,
    confiança 92%."
    """

    lancamento_id: UUID
    ambiente_id: UUID | None
    ambiente_nome: str | None

    inicio: datetime
    fim: datetime
    duracao_minutos: int

    total_eventos: int
    presenca_detectada: bool
    contagem_pessoas_max: int | None
    contagem_pessoas_media: float | None
    quedas_detectadas: int
    distress_detectado: int
    paciente_deitado_pct: float | None = Field(
        default=None,
        description="Percentual do tempo com 'paciente deitado/POSE=DEITADO' (0..1).",
    )

    bpm_medio: float | None = None
    rpm_medio: float | None = None

    veredito: str = Field(
        description=(
            "VALIDO | AUDITORIA | INSUFICIENTE — sugestão automática "
            "para o operador decidir."
        )
    )
    motivos: list[str] = Field(
        default_factory=list,
        description="Razões legíveis que justificam o veredito.",
    )


# ============================================================
# Dashboard / Stats agregadas
# ============================================================


class VitalStats(BaseModel):
    """Resumo executivo do módulo (página inicial)."""

    cliente_id: UUID
    nos_total: int
    nos_online: int
    nos_offline: int
    ambientes_total: int
    eventos_24h: int
    quedas_24h: int
    distress_24h: int
    ultima_atividade: datetime | None


class NoHeartbeat(BaseModel):
    """Resposta enxuta pro front mostrar 'nó vivo / morto'."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    node_id: str
    apelido: str | None
    status: StatusNo
    last_seen_at: datetime | None
    ambiente_id: UUID | None


# ============================================================
# Filtros de query (params reaproveitados)
# ============================================================


class EventoFiltro(BaseModel):
    """Filtros aceitos no GET /vital/eventos (não é body, é query param)."""

    cliente_id: UUID | None = None
    ambiente_id: UUID | None = None
    no_id: UUID | None = None
    tipo: TipoEvento | None = None
    de: datetime | None = None
    ate: datetime | None = None
    data: date | None = None
    limite: int = Field(default=200, ge=1, le=2000)
    offset: int = Field(default=0, ge=0)


__all__ = [
    "AmbienteCreate",
    "AmbienteOut",
    "AmbienteUpdate",
    "AuditoriaResumo",
    "EventoFiltro",
    "EventoIngest",
    "EventoIngestLote",
    "EventoListResponse",
    "EventoOut",
    "IngestResult",
    "NoComApiKey",
    "NoCreate",
    "NoHeartbeat",
    "NoOut",
    "NoUpdate",
    "VitalStats",
]
