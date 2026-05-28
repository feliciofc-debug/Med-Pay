"""Módulo MedPag Vital — monitoramento de presença e sinais vitais.

Recebe eventos de sensores físicos (RuView/ESP32 com WiFi CSI sensing, Aqara
FP2 com mmWave, ou qualquer outro hardware compatível) e armazena tudo num
schema genérico que permite cruzar com `lancamentos_servico` pra antifraude.

Conceitos:
    AmbienteMonitorado: lugar físico (sala cirúrgica 3, UTI leito 12, etc).
    NoVital: um sensor de hardware registrado (1 ESP32 = 1 nó).
    EventoVital: cada leitura/evento recebido do sensor.

Privacidade (LGPD by design):
    Os sensores RuView podem rodar em --privacy-mode, onde só primitivas
    semânticas chegam ("alguém-caiu", "sala-ocupada") sem dados biométricos
    brutos. O modelo aceita os dois — `tipo` discrimina.

Antifraude:
    Médico lança procedimento "Cesárea 14h-15h30 sala 3"
        → Buscamos EventoVital(ambiente=sala3, periodo=14h-15h30)
        → Vemos quantas pessoas no recinto, se uma deitada estável (paciente)
        → Cruzamos com presença detectada via BLE/selfie
        → Se tudo bate: VÁLIDO. Se não: ENTRA NA AUDITORIA.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cliente import Cliente


# ============================================================
# Enums
# ============================================================


class TipoAmbiente(str, Enum):
    """Categoria do ambiente monitorado."""

    SALA_CIRURGICA = "SALA_CIRURGICA"
    UTI = "UTI"
    ENFERMARIA = "ENFERMARIA"
    CONSULTORIO = "CONSULTORIO"
    PRONTO_SOCORRO = "PRONTO_SOCORRO"
    RESIDENCIAL = "RESIDENCIAL"  # home care, casa do médico em testes
    OUTRO = "OUTRO"


class TipoSensor(str, Enum):
    """Modelo de hardware do sensor."""

    RUVIEW_ESP32_S3 = "RUVIEW_ESP32_S3"
    RUVIEW_ESP32_C6 = "RUVIEW_ESP32_C6"
    AQARA_FP2 = "AQARA_FP2"
    AQARA_FP1 = "AQARA_FP1"
    SIMULADO = "SIMULADO"  # docker run --source sim — pra demos sem hardware
    OUTRO = "OUTRO"


class StatusNo(str, Enum):
    """Estado de conectividade do nó."""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    DEGRADADO = "DEGRADADO"  # respondendo mas com falhas / latência alta
    NUNCA_VISTO = "NUNCA_VISTO"  # cadastrado mas nunca enviou evento


class TipoEvento(str, Enum):
    """Tipo do evento recebido do sensor.

    Cobre tanto sinais brutos do RuView (HR, BR, contagem) quanto primitivas
    semânticas (alguém-caiu, sala-ocupada, anomalia-inatividade).
    """

    # ----- Brutos -----
    PRESENCA = "PRESENCA"  # bool: tem alguém?
    CONTAGEM_PESSOAS = "CONTAGEM_PESSOAS"  # int: quantos
    MOVIMENTO = "MOVIMENTO"  # float 0..1: intensidade
    BATIMENTO_CARDIACO = "BATIMENTO_CARDIACO"  # int: bpm
    FREQUENCIA_RESPIRATORIA = "FREQUENCIA_RESPIRATORIA"  # int: rpm
    QUEDA = "QUEDA"  # bool: queda detectada
    POSE = "POSE"  # texto: "EM_PE", "SENTADO", "DEITADO"

    # ----- Semânticos (RuView /ws/sensing) -----
    PESSOA_DORMINDO = "PESSOA_DORMINDO"
    POSSIVEL_DISTRESS = "POSSIVEL_DISTRESS"  # respiração/batimento anormal
    SALA_ATIVA = "SALA_ATIVA"
    ANOMALIA_INATIVIDADE = "ANOMALIA_INATIVIDADE"  # idoso parado tempo demais
    REUNIAO = "REUNIAO"  # várias pessoas conversando
    BANHEIRO = "BANHEIRO"
    RISCO_QUEDA = "RISCO_QUEDA"  # movimento sugestivo de instabilidade
    SAIDA_CAMA = "SAIDA_CAMA"
    SEM_MOVIMENTO = "SEM_MOVIMENTO"
    TRANSICAO_MULTI_SALA = "TRANSICAO_MULTI_SALA"

    # ----- Operacionais -----
    HEARTBEAT = "HEARTBEAT"  # nó "vivo" — não conta como evento clínico
    OUTRO = "OUTRO"


# ============================================================
# AmbienteMonitorado
# ============================================================


class AmbienteMonitorado(Base):
    """Lugar físico sendo monitorado (sala cirúrgica, UTI, etc).

    Escopo por cliente — cada hospital/operação tem os seus.
    """

    __tablename__ = "vital_ambientes"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    cliente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[TipoAmbiente] = mapped_column(
        SAEnum(
            TipoAmbiente,
            name="vital_tipo_ambiente",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=False,
        default=TipoAmbiente.OUTRO,
    )

    descricao: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    referencia_externa: Mapped[str | None] = mapped_column(
        String(120), nullable=True,
        comment="Código do hospital/prefeitura, ex: 'CC-3', 'UTI-LEITO-12'",
    )

    ativo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", lazy="joined")

    __table_args__ = (
        UniqueConstraint(
            "cliente_id", "nome", name="uq_vital_ambiente_cliente_nome"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AmbienteMonitorado id={self.id} nome={self.nome} "
            f"tipo={self.tipo.value} cliente={self.cliente_id}>"
        )


# ============================================================
# NoVital (hardware sensor)
# ============================================================


class NoVital(Base):
    """Um sensor físico cadastrado (1 chip = 1 nó).

    O `api_key` é o token que o ESP32 manda no header `X-Vital-Node-Token`
    pra autenticar a ingestão de eventos. Sem cookie, sem JWT — é IoT.
    """

    __tablename__ = "vital_nos"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    cliente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    ambiente_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("vital_ambientes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Nó pode estar 'em estoque' (sem ambiente atribuído ainda).",
    )

    node_id: Mapped[str] = mapped_column(
        String(120), nullable=False,
        comment="ID lógico que o sensor manda no payload (ex: 'esp32-001').",
    )

    tipo: Mapped[TipoSensor] = mapped_column(
        SAEnum(
            TipoSensor,
            name="vital_tipo_sensor",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=False,
        default=TipoSensor.RUVIEW_ESP32_S3,
    )

    apelido: Mapped[str | None] = mapped_column(String(255), nullable=True)

    api_key: Mapped[str] = mapped_column(
        String(120), nullable=False, unique=True, index=True,
        comment="Segredo enviado pelo nó no header X-Vital-Node-Token.",
    )

    status: Mapped[StatusNo] = mapped_column(
        SAEnum(
            StatusNo,
            name="vital_status_no",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=False,
        default=StatusNo.NUNCA_VISTO,
        server_default=StatusNo.NUNCA_VISTO.value,
    )

    privacy_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
        comment="Se True, nó deve enviar só primitivas semânticas (sem HR/BR brutos).",
    )

    firmware_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_rssi: Mapped[float | None] = mapped_column(Float, nullable=True)

    ativo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", lazy="joined")
    ambiente: Mapped["AmbienteMonitorado | None"] = relationship(
        "AmbienteMonitorado", lazy="joined"
    )

    __table_args__ = (
        UniqueConstraint(
            "cliente_id", "node_id", name="uq_vital_no_cliente_node"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<NoVital id={self.id} node_id={self.node_id} "
            f"tipo={self.tipo.value} status={self.status.value}>"
        )


# ============================================================
# EventoVital
# ============================================================


class EventoVital(Base):
    """Cada leitura/evento recebido de um nó.

    Modelo deliberadamente GENÉRICO: `tipo` discrimina, `valor_num` e
    `valor_texto` carregam o payload, `confianca` é o score de IA do sensor.

    Performance:
        Esperamos ~20 eventos/s por nó. Em 24h, 1 nó = ~1.7M eventos.
        Os índices abaixo cobrem as queries principais:
            (cliente_id, observado_em) — feed do dashboard
            (ambiente_id, observado_em) — timeline da sala
            (no_id, observado_em) — saúde do nó
            (tipo, observado_em) — filtros por categoria (todas as quedas, etc)
    """

    __tablename__ = "vital_eventos"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    cliente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    ambiente_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("vital_ambientes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    no_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("vital_nos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    tipo: Mapped[TipoEvento] = mapped_column(
        SAEnum(
            TipoEvento,
            name="vital_tipo_evento",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=False,
        index=True,
    )

    valor_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    valor_texto: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confianca: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Score de confiança da inferência (0..1).",
    )

    observado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
        comment="Timestamp no relógio do sensor (não confundir com created_at).",
    )

    extras_json: Mapped[str | None] = mapped_column(
        String(2048), nullable=True,
        comment="JSON livre — payload extra do sensor (pose keypoints, etc).",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", lazy="joined")
    ambiente: Mapped["AmbienteMonitorado | None"] = relationship(
        "AmbienteMonitorado", lazy="select"
    )
    no: Mapped["NoVital | None"] = relationship("NoVital", lazy="select")

    __table_args__ = (
        Index("ix_vital_eventos_cliente_obs", "cliente_id", "observado_em"),
        Index("ix_vital_eventos_ambiente_obs", "ambiente_id", "observado_em"),
        Index("ix_vital_eventos_no_obs", "no_id", "observado_em"),
        Index("ix_vital_eventos_tipo_obs", "tipo", "observado_em"),
    )

    def __repr__(self) -> str:
        return (
            f"<EventoVital id={self.id} tipo={self.tipo.value} "
            f"ambiente={self.ambiente_id} observado_em={self.observado_em}>"
        )


__all__ = [
    "AmbienteMonitorado",
    "EventoVital",
    "NoVital",
    "StatusNo",
    "TipoAmbiente",
    "TipoEvento",
    "TipoSensor",
]
