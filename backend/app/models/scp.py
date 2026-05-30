"""Modelos da Sociedade em Conta de Participação (SCP).

Materializa o modelo de negócio onde a MedPag opera como sócio ostensivo
e os médicos são sócios participantes (ver mapa mental — "Modelo SCP").
O repasse deixa de ser "pagamento por serviço" e vira DISTRIBUIÇÃO DE
RESULTADO.

Três entidades:

    ParticipanteSCP  — vínculo médico ↔ SCP, com a regra de cota.
    ApuracaoSCP      — fechamento de um período (receita − custos = resultado).
    DistribuicaoSCP  — quanto cada participante recebe naquela apuração.

Importante: o dinheiro sai SEMPRE por banco tradicional (a distribuição
vira lote/CNAB). A SCP só apura e instrui — nada disso passa pelo Asaas.

Escopo multi-tenant: `cliente_id` aponta pro tenant da SCP (tipo
MEDPAG_REPASSE). Os médicos são `Beneficiario` do mesmo cliente.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.beneficiario import Beneficiario
    from app.models.cliente import Cliente
    from app.models.lote import Lote


class RegraCota(str, Enum):
    """Como a parte de cada médico participante é calculada.

    PERCENTUAL_FIXO     — contrato define um % fixo do resultado
                          (usa `percentual_bp`, em basis points).
    PROPORCIONAL_SERVICO — proporcional ao que o médico produziu no
                          período (via CRM/lançamentos). É o mais
                          "MedPag": automático e auditável.
    POR_APORTE          — proporcional ao capital aportado
                          (usa `aporte_centavos`).
    """

    PERCENTUAL_FIXO = "PERCENTUAL_FIXO"
    PROPORCIONAL_SERVICO = "PROPORCIONAL_SERVICO"
    POR_APORTE = "POR_APORTE"


class StatusApuracaoSCP(str, Enum):
    """Ciclo de vida de uma apuração de resultado da SCP."""

    ABERTA = "ABERTA"            # ainda recebendo lançamentos do período
    FECHADA = "FECHADA"          # resultado calculado, pronto pra distribuir
    DISTRIBUIDA = "DISTRIBUIDA"  # distribuição gerada (virou lote/CNAB)


class ParticipanteSCP(Base):
    """Médico sócio participante de uma SCP."""

    __tablename__ = "scp_participantes"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # Tenant da SCP (cliente tipo MEDPAG_REPASSE).
    cliente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # O médico, no cadastro mestre de beneficiários.
    beneficiario_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("beneficiarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    regra_cota: Mapped[RegraCota] = mapped_column(
        SAEnum(
            RegraCota,
            name="regra_cota_scp",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=False,
        default=RegraCota.PROPORCIONAL_SERVICO,
        server_default=RegraCota.PROPORCIONAL_SERVICO.value,
    )

    # Cota fixa em basis points (10000 = 100%). Só usado quando
    # regra_cota = PERCENTUAL_FIXO.
    percentual_bp: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Capital aportado em centavos. Só usado quando regra_cota = POR_APORTE.
    aporte_centavos: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )

    # Vigência da participação (pra entrada/saída de sócios no meio).
    vigencia_inicio: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    vigencia_fim: Mapped[date | None] = mapped_column(Date, nullable=True)

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

    beneficiario: Mapped["Beneficiario"] = relationship("Beneficiario", lazy="joined")

    __table_args__ = (
        UniqueConstraint(
            "cliente_id", "beneficiario_id", name="uq_scp_participante"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ParticipanteSCP cliente={self.cliente_id} "
            f"benef={self.beneficiario_id} regra={self.regra_cota.value}>"
        )


class ApuracaoSCP(Base):
    """Apuração de resultado da SCP num período (competência YYYY-MM)."""

    __tablename__ = "scp_apuracoes"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    cliente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Competência no formato YYYY-MM (ex.: "2026-05").
    competencia: Mapped[str] = mapped_column(String(7), nullable=False, index=True)

    # Receita bruta operada no período (o que entrou na conta da SCP).
    receita_bruta_centavos: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    # Custos do período (operação, taxa MedPag, etc.).
    custos_centavos: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    # Resultado distribuível = receita_bruta − custos (derivado no fechamento).
    resultado_centavos: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )

    status: Mapped[StatusApuracaoSCP] = mapped_column(
        SAEnum(
            StatusApuracaoSCP,
            name="status_apuracao_scp",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=False,
        default=StatusApuracaoSCP.ABERTA,
        server_default=StatusApuracaoSCP.ABERTA.value,
        index=True,
    )

    # Lote gerado quando a distribuição é executada (vira CNAB).
    lote_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("lotes.id", ondelete="SET NULL"),
        nullable=True,
    )

    observacoes: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    distribuicoes: Mapped[list["DistribuicaoSCP"]] = relationship(
        "DistribuicaoSCP",
        back_populates="apuracao",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "cliente_id", "competencia", name="uq_scp_apuracao_competencia"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ApuracaoSCP cliente={self.cliente_id} comp={self.competencia} "
            f"resultado={self.resultado_centavos}c status={self.status.value}>"
        )


class DistribuicaoSCP(Base):
    """Quanto um participante recebe numa apuração (linha da distribuição)."""

    __tablename__ = "scp_distribuicoes"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    apuracao_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("scp_apuracoes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    participante_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("scp_participantes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    beneficiario_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("beneficiarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Base usada no rateio (ex.: serviço do médico no período, ou aporte).
    base_centavos: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    # % efetivo aplicado, em basis points (pra transparência/auditoria).
    percentual_aplicado_bp: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Valor distribuído ao participante, em centavos.
    valor_centavos: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    apuracao: Mapped["ApuracaoSCP"] = relationship(
        "ApuracaoSCP", back_populates="distribuicoes"
    )

    def __repr__(self) -> str:
        return (
            f"<DistribuicaoSCP apuracao={self.apuracao_id} "
            f"benef={self.beneficiario_id} valor={self.valor_centavos}c>"
        )


__all__ = [
    "ApuracaoSCP",
    "DistribuicaoSCP",
    "ParticipanteSCP",
    "RegraCota",
    "StatusApuracaoSCP",
]
