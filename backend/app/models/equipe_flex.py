"""Equipe Flex — banco de horas compartilhado entre médicos.

Modelo de operação observado em hospitais públicos (caso real:
Hospital do Cérebro / Sandro):

    - Hospital tem uma equipe (ex.: 10 plantonistas de UTI)
    - No mês, a equipe acumula um total de horas
    - O valor bruto = horas_total × valor_hora
    - O valor é dividido EM PARTES IGUAIS entre os N membros ativos
    - Os médicos resolvem internamente quem trabalhou mais ou menos

Diferente do modelo "uma ficha = N pagamentos individuais", aqui:
    - O coordenador (Sandro) só precisa cadastrar quanto a equipe
      trabalhou no mês.
    - O sistema gera automaticamente um pagamento por membro,
      todos com o mesmo valor.
    - Banco de horas individual fica fora do escopo (eles ajustam
      por fora).

O fechamento gera um Lote no pipeline normal de pagamento (CNAB,
aprovação, etc.).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cliente import Cliente
    from app.models.lote import Lote
    from app.models.user import User


class EquipeFlex(Base):
    """Conjunto de profissionais que compartilham banco de horas em um hospital."""

    __tablename__ = "equipes_flex"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    cliente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    # Categoria livre: "Plantonista", "Cirurgião", "Enfermeiro" etc.
    # Não é FK pra dar flexibilidade nos primeiros clientes.
    categoria: Mapped[str] = mapped_column(String(80), nullable=False, default="Plantonista")
    # Quanto vale 1 hora dessa equipe (antes do desconto MedPag).
    valor_hora_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ativa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
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

    cliente: Mapped["Cliente"] = relationship("Cliente", lazy="joined")
    membros: Mapped[list["MembroEquipe"]] = relationship(
        "MembroEquipe",
        back_populates="equipe",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    fechamentos: Mapped[list["FechamentoEquipe"]] = relationship(
        "FechamentoEquipe",
        back_populates="equipe",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<EquipeFlex {self.nome!r} cliente={self.cliente_id}>"


class MembroEquipe(Base):
    """Médico/profissional que faz parte de uma equipe flex."""

    __tablename__ = "membros_equipe"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    equipe_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("equipes_flex.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    cpf: Mapped[str] = mapped_column(String(11), nullable=False)
    crm_ou_registro: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Pagamento — o membro pode usar PIX OU dados bancários
    chave_pix: Mapped[str | None] = mapped_column(String(120), nullable=True)
    banco_codigo: Mapped[str | None] = mapped_column(String(3), nullable=True)
    agencia: Mapped[str | None] = mapped_column(String(10), nullable=True)
    conta: Mapped[str | None] = mapped_column(String(20), nullable=True)
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

    equipe: Mapped["EquipeFlex"] = relationship("EquipeFlex", back_populates="membros")

    __table_args__ = (
        UniqueConstraint("equipe_id", "cpf", name="uq_membro_equipe_cpf"),
    )

    def __repr__(self) -> str:
        return f"<MembroEquipe {self.nome!r} equipe={self.equipe_id}>"


class FechamentoEquipe(Base):
    """Fechamento mensal de uma equipe — origem do lote de pagamento.

    Snapshot dos membros no momento do fechamento (`qtd_membros`)
    garante que mudanças posteriores na equipe não distorçam a
    divisão histórica.
    """

    __tablename__ = "fechamentos_equipe"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    equipe_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("equipes_flex.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Formato YYYY-MM (ex.: "2026-06"). Único por equipe.
    competencia: Mapped[str] = mapped_column(String(7), nullable=False)
    horas_total: Mapped[int] = mapped_column(Integer, nullable=False)
    valor_hora_centavos: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # snapshot do valor/hora no momento do fechamento
    valor_bruto_centavos: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # = horas_total * valor_hora_centavos
    desconto_medpag_centavos: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )  # 0 quando hospital é mensalidade SaaS
    valor_liquido_centavos: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # bruto - desconto = total a dividir entre membros
    qtd_membros: Mapped[int] = mapped_column(Integer, nullable=False)
    valor_por_membro_centavos: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # = valor_liquido / qtd_membros (arredondado pra baixo)

    # Origem do dado
    # "DIGITACAO" — Sandro digitou as horas
    # "FICHA_OCR" — veio de uma ficha enviada pelo coordenador
    origem: Mapped[str] = mapped_column(String(20), nullable=False, default="DIGITACAO")
    ficha_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("fichas_plantao.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Lote gerado quando confirma o fechamento. NULL = ainda em rascunho.
    lote_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("lotes.id", ondelete="SET NULL"),
        nullable=True,
    )

    aprovado_por_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    aprovado_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    equipe: Mapped["EquipeFlex"] = relationship("EquipeFlex", back_populates="fechamentos")
    aprovado_por: Mapped["User | None"] = relationship("User", lazy="joined")
    lote: Mapped["Lote | None"] = relationship("Lote", lazy="select")

    __table_args__ = (
        UniqueConstraint(
            "equipe_id", "competencia", name="uq_fechamento_equipe_competencia"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<FechamentoEquipe equipe={self.equipe_id} "
            f"comp={self.competencia} bruto={self.valor_bruto_centavos}c>"
        )


__all__ = ["EquipeFlex", "MembroEquipe", "FechamentoEquipe"]
