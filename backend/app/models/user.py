"""Modelo de usuário do sistema (operadores e aprovadores)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.auditoria import Auditoria
    from app.models.cliente import Cliente
    from app.models.lote import Lote


class UserRole(str, Enum):
    """Papéis disponíveis no sistema.

    Visão MedPag (cliente_id=NULL):
    - ADMIN: Felício e equipe interna MedPag. Gerencia tudo: usuários,
      clientes, planos, vê o Super Admin / Executivo.
    - APROVADOR: pode aprovar lotes e gerar CNAB no MedPag central.
    - OPERADOR: pode revisar lotes (4 olhos antes da aprovação).

    Visão Hospital (cliente_id=UUID):
    - COORDENADOR: funcionário do hospital que SOBE fichas/planilhas
      dos plantões. Vê só o que ele mesmo subiu. Ponto de entrada da
      operação. Não aprova.
    - GESTOR: gestor do hospital — vê tudo do hospital, aprova
      fechamento de período. NÃO mexe em CNAB (delega ao Financeiro).
    - FINANCEIRO: financeiro do hospital — baixa extrato, gera CNAB
      ou folha de pagamento. Não decide quem é pago, só executa.
    - MEDICO: prestador (médico/enfermeiro) — vê só os PRÓPRIOS
      plantões, extrato e pagamentos. Não vê dados de outros.
    """

    ADMIN = "ADMIN"
    APROVADOR = "APROVADOR"
    OPERADOR = "OPERADOR"
    COORDENADOR = "COORDENADOR"
    GESTOR = "GESTOR"
    FINANCEIRO = "FINANCEIRO"
    MEDICO = "MEDICO"


class User(Base):
    """Usuário do sistema."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"),
        nullable=False,
        default=UserRole.OPERADOR,
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ---------- Multi-tenancy ----------
    # cliente_id = null  → "MedPag interno" (admin global, vê tudo)
    #            = UUID  → user pertence a esse cliente, queries são filtradas
    # Setado automaticamente no signup self-service (/api/signup).
    # Users criados por admin MedPag (via /admin) nascem com null.
    cliente_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ---------- Vinculo com Beneficiario (so para role MEDICO) ----------
    # Quando role == MEDICO, este id aponta pro cadastro de prestador
    # (Beneficiario) deste medico no hospital. Permite ao app do medico
    # filtrar plantoes/extrato pelo seu proprio CPF sem expor o numero.
    # Pode ser null se o medico ainda nao foi vinculado (UI mostra aviso).
    beneficiario_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("beneficiarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relacionamentos
    cliente: Mapped["Cliente | None"] = relationship(
        "Cliente", foreign_keys=[cliente_id]
    )
    beneficiario: Mapped["Beneficiario | None"] = relationship(  # noqa: F821
        "Beneficiario", foreign_keys=[beneficiario_id]
    )
    lotes_enviados: Mapped[list["Lote"]] = relationship(
        "Lote", back_populates="enviado_por", foreign_keys="Lote.enviado_por_id"
    )
    lotes_aprovados: Mapped[list["Lote"]] = relationship(
        "Lote", back_populates="aprovado_por", foreign_keys="Lote.aprovado_por_id"
    )
    eventos_auditoria: Mapped[list["Auditoria"]] = relationship(
        "Auditoria", back_populates="user"
    )

    @property
    def pode_aprovar(self) -> bool:
        """Apenas APROVADOR e ADMIN podem aprovar lotes."""
        return self.role in (UserRole.APROVADOR, UserRole.ADMIN)

    @property
    def is_medpag_interno(self) -> bool:
        """User MedPag (sem cliente_id) — vê todos os tenants.

        Usado pelo `get_tenant_filter` pra decidir se aplica filtro
        por cliente_id nas queries.
        """
        return self.cliente_id is None

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role.value}>"
