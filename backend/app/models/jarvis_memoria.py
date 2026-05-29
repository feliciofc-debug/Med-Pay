"""Memória persistente do Jarvis — fatos, preferências, decisões.

Diferente do `WhatsAppMensagem` (que é log bruto da conversa, expira após
24h pro contexto), aqui ficam itens que o Jarvis decide REALMENTE
guardar pra usar de novo dali a semanas. Exemplos:

- "Felício prefere relatório de pipeline às segundas de manhã"
- "Cliente Auris paga via PIX direto, não Unicred"
- "Decidimos não aceitar trial pra hospital com menos de 50 leitos"
- "Bug conhecido: ficha de UTI Norte sempre vem com data trocada"

Carregamos as N memórias mais recentes/relevantes no system prompt a
cada conversa, dando ao Jarvis continuidade entre sessões.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class TipoMemoria(str, Enum):
    """Categoria do que está sendo lembrado."""

    PREFERENCIA = "PREFERENCIA"   # Como o usuário gosta das coisas
    FATO = "FATO"                  # Informação concreta sobre operação/cliente
    DECISAO = "DECISAO"            # Decisão estratégica tomada
    NOTA = "NOTA"                  # Observação solta, contexto


class JarvisMemoria(Base):
    """Item de memória do Jarvis vinculado a um usuário.

    Multi-tenancy: cada User tem suas memórias próprias. ADMIN MedPag
    (cliente_id=NULL) usa as memórias dele; um Gestor de hospital usa
    as dele. Sem cruzamento.
    """

    __tablename__ = "jarvis_memorias"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tipo: Mapped[TipoMemoria] = mapped_column(
        SAEnum(TipoMemoria, name="tipo_memoria_jarvis"),
        nullable=False,
        default=TipoMemoria.NOTA,
        index=True,
    )

    # Texto livre da memória (o Jarvis escolhe como redigir)
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)

    # Tags pra ajudar a recuperar (ex: "auris,pix,banco" → buscar
    # memórias relacionadas a um cliente específico). Separadas por vírgula.
    tags: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relevância 1-10 (Jarvis define quando salva; mais alto = sempre
    # presente no contexto). Default 5.
    relevancia: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5
    )

    # Soft-delete (Jarvis pode "esquecer" sem deletar registro)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<JarvisMemoria {self.tipo.value} user={self.user_id} "
            f"rel={self.relevancia} '{self.conteudo[:40]}...'>"
        )


__all__ = ["JarvisMemoria", "TipoMemoria"]
