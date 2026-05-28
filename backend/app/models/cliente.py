"""Modelo de Cliente (hospital, clínica, ONG que envia planilhas)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.plano import Plano, StatusAssinatura

if TYPE_CHECKING:
    from app.models.lote import Lote


class Cliente(Base):
    """Cliente que envia planilhas de pagamento.

    Tipicamente um hospital, clínica ou ONG. Cada cliente pode ter
    formato próprio de planilha — o mapeamento de colunas é salvo
    em `mapeamento_colunas` (JSON) pra reaproveitar.
    """

    __tablename__ = "clientes"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    nome: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True, unique=True, index=True)
    email_contato: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Email autorizado a enviar planilhas (whitelist)
    # Quando email chega de um remetente nesta lista, sistema identifica o cliente
    email_remetente_autorizado: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    # Mapeamento de colunas da planilha deste cliente
    # Ex: {"cpf": "Documento", "nome": "Beneficiário", "valor": "Valor Bruto", ...}
    mapeamento_colunas: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # ---------- Plano + Assinatura ----------
    # Cada cliente assina um plano que define features padrão e limites.
    # Nullable porque clientes legados nascem sem plano e migram depois.
    plano_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("planos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Overrides pontuais do plano (ex: cliente Profissional com Sentinela
    # liberado por cortesia). Dict no mesmo formato do Plano.features.
    # Vazio = usa tudo do plano. Resolver checa override antes do plano.
    features_override: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Overrides do cliente sobre o plano. Vazio = usa só o plano.",
    )

    status_assinatura: Mapped[StatusAssinatura] = mapped_column(
        SAEnum(
            StatusAssinatura,
            name="status_assinatura",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=StatusAssinatura.ATIVO,
        server_default=StatusAssinatura.ATIVO.value,
        index=True,
    )

    # Setado quando cliente nasce em TRIAL. Null fora desse estado.
    trial_termina_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relacionamentos
    lotes: Mapped[list["Lote"]] = relationship("Lote", back_populates="cliente")
    plano: Mapped["Plano | None"] = relationship("Plano", lazy="joined")

    def __repr__(self) -> str:
        return f"<Cliente id={self.id} nome={self.nome}>"
