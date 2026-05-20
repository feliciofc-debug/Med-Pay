"""Modelo de usuário do sistema (operadores e aprovadores)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.auditoria import Auditoria
    from app.models.lote import Lote


class UserRole(str, Enum):
    """Papéis disponíveis no sistema.

    - APROVADOR: pode aprovar lotes e gerar CNAB (Thiago, dono)
    - OPERADOR: pode revisar lotes, mas não aprova (funcionário)
    - ADMIN: gerencia usuários, clientes, configurações
    """

    ADMIN = "ADMIN"
    APROVADOR = "APROVADOR"
    OPERADOR = "OPERADOR"


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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relacionamentos
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

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role.value}>"
