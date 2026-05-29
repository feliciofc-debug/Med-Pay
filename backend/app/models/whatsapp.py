"""Modelos do módulo Jarvis — WhatsApp + LLM.

Três tabelas:

- `WhatsAppUser`: whitelist de telefones autorizados a falar com o Jarvis.
  Cada telefone vinculado a um `User` da plataforma — assim o Jarvis sabe
  qual o role (ADMIN só admin pode aprovar, etc) e respeita as permissões.

- `WhatsAppMensagem`: log de TODAS as mensagens (in/out). Importante para
  auditoria, ainda mais com aprovação financeira via WhatsApp acontecendo.

- `WhatsAppInstancia`: a sessão Wuzapi do MedPag (linha única por enquanto).
  Mantém o número de WhatsApp pareado e o token gerado.

Filosofia: o Jarvis é um sócio digital com acesso total à operação. Tudo
o que ele faz tem que ficar gravado, com timestamp + user_id, prontíssimo
pra auditar em caso de disputa.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class DirecaoMensagem(str, Enum):
    """De quem partiu a mensagem."""

    INBOUND = "INBOUND"   # Usuário → Jarvis
    OUTBOUND = "OUTBOUND"  # Jarvis → Usuário


class StatusInstancia(str, Enum):
    """Estado da sessão Wuzapi."""

    DESCONECTADA = "DESCONECTADA"
    AGUARDANDO_QR = "AGUARDANDO_QR"
    CONECTADA = "CONECTADA"
    ERRO = "ERRO"


class WhatsAppUser(Base):
    """Telefone autorizado a falar com o Jarvis.

    Sem registro nessa tabela, o webhook ignora a mensagem. Isso garante
    que apenas pessoas previamente cadastradas (Felício, Thiago, sócios
    futuros) tenham acesso ao agente.

    O telefone é normalizado em `numero_e164` (ex: 5521999998888) — sem
    `+`, sem hífens, sem espaços. Validação no service.
    """

    __tablename__ = "whatsapp_users"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    # Formato E.164 sem +, ex: "5521999998888"
    numero_e164: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True, index=True
    )
    apelido: Mapped[str | None] = mapped_column(String(100), nullable=True)

    pode_aprovar_pagamento: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # ^ flag explícita: só quem ADMIN + tem essa flag aprova lote pelo zap.
    # Não confiamos em só checar role pra essa ação especifíca.

    # Opt-in pra Jarvis enviar diagnostico todo dia 8h (Sao Paulo)
    receber_relatorio_diario: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relacionamento
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<WhatsAppUser tel={self.numero_e164} user_id={self.user_id}>"


class WhatsAppMensagem(Base):
    """Mensagem do WhatsApp (in ou out) — log completo pra auditoria."""

    __tablename__ = "whatsapp_mensagens"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Telefone que enviou OU recebeu (sempre o do humano, nunca do bot)
    numero_e164: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # User vinculado, se identificado (mensagem de número não autorizado
    # também é gravada, com user_id NULL — útil pra detectar tentativas
    # de acesso indevido).
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )

    direcao: Mapped[DirecaoMensagem] = mapped_column(
        SAEnum(DirecaoMensagem, name="direcao_mensagem"),
        nullable=False,
        index=True,
    )

    texto: Mapped[str] = mapped_column(Text, nullable=False)

    # ID da mensagem no Wuzapi/WhatsApp (pra dedupe de webhook)
    wuzapi_message_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )

    # Tools chamadas pelo LLM nesta interação (lista JSON de
    # {tool, args, resultado}). Útil pra auditar "o Jarvis aprovou o
    # lote X com base em Y".
    tools_usadas: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True
    )

    # Tokens consumidos no Groq nessa chamada (custo)
    tokens_prompt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_resposta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duracao_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Erro durante processamento (se houver)
    erro: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    user: Mapped["User | None"] = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<WhatsAppMensagem {self.direcao.value} tel={self.numero_e164} "
            f"chars={len(self.texto)}>"
        )


class WhatsAppInstancia(Base):
    """Sessão Wuzapi do MedPag.

    Por enquanto guardamos apenas uma linha (singleton lógico). No futuro
    podemos ter múltiplas instâncias (uma por cliente do BPO), mas pra
    MVP é só o "WhatsApp do Jarvis".
    """

    __tablename__ = "whatsapp_instancias"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identificador da instância no Wuzapi
    wuzapi_instance_id: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    # Token criado quando a instância foi provisionada no Wuzapi
    wuzapi_token: Mapped[str] = mapped_column(String(255), nullable=False)

    # Telefone que aparece como "remetente" pros usuários (preenchido
    # quando QR code é escaneado).
    numero_bot: Mapped[str | None] = mapped_column(String(20), nullable=True)

    status: Mapped[StatusInstancia] = mapped_column(
        SAEnum(StatusInstancia, name="status_instancia_wpp"),
        nullable=False,
        default=StatusInstancia.DESCONECTADA,
    )

    # Último QR code gerado (só persistimos pra debug — expira em ~60s)
    ultimo_qr_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    ultimo_qr_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

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

    def __repr__(self) -> str:
        return (
            f"<WhatsAppInstancia id={self.wuzapi_instance_id} "
            f"status={self.status.value} tel={self.numero_bot}>"
        )


__all__ = [
    "DirecaoMensagem",
    "StatusInstancia",
    "WhatsAppInstancia",
    "WhatsAppMensagem",
    "WhatsAppUser",
]
