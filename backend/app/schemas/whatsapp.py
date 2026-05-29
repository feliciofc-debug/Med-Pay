"""Schemas Pydantic do módulo Jarvis (WhatsApp)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.whatsapp import DirecaoMensagem, StatusInstancia
from app.models.user import UserRole


# ============================================================
# WhatsAppUser (whitelist)
# ============================================================


class WhatsAppUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    user_nome: str
    user_email: str
    user_role: UserRole
    numero_e164: str
    apelido: str | None
    pode_aprovar_pagamento: bool
    receber_relatorio_diario: bool = False
    ativo: bool
    created_at: datetime


class CriarWhatsAppUserRequest(BaseModel):
    user_id: UUID
    numero_e164: str = Field(
        ...,
        min_length=10,
        max_length=20,
        description="Telefone E.164 sem +, ex: 5521999998888",
    )
    apelido: str | None = None
    pode_aprovar_pagamento: bool = False
    receber_relatorio_diario: bool = False


class AtualizarWhatsAppUserRequest(BaseModel):
    apelido: str | None = None
    pode_aprovar_pagamento: bool | None = None
    receber_relatorio_diario: bool | None = None
    ativo: bool | None = None


# ============================================================
# Mensagem (histórico)
# ============================================================


class WhatsAppMensagemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    numero_e164: str
    user_id: UUID | None
    direcao: DirecaoMensagem
    texto: str
    tools_usadas: list[dict[str, Any]] | None
    tokens_prompt: int
    tokens_resposta: int
    duracao_ms: int
    erro: str | None
    created_at: datetime


# ============================================================
# Instância Wuzapi
# ============================================================


class InstanciaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wuzapi_instance_id: str
    numero_bot: str | None
    status: StatusInstancia
    ativa: bool
    created_at: datetime
    updated_at: datetime


class QRCodeOut(BaseModel):
    qr_base64: str | None
    status: StatusInstancia


class AdotarInstanciaRequest(BaseModel):
    """Adota uma instancia ja existente no servidor Wuzapi.

    Quando o admin gerou o QR code direto no servidor (via curl/UI do
    Wuzapi) e ja pareou o WhatsApp, podemos plugar essa instancia no
    Med-Pay sem precisar criar nada novo. Basta colar o `instance_id`
    e o `token` que o Wuzapi gerou.
    """

    wuzapi_instance_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="ID/nome do user no servidor Wuzapi (ex: 'medpag-jarvis' ou um UUID)",
    )
    wuzapi_token: str = Field(
        ...,
        min_length=8,
        max_length=255,
        description="Token da instancia, gerado pelo Wuzapi quando o user foi criado",
    )
    numero_bot: str | None = Field(
        None,
        max_length=20,
        description="Telefone do WhatsApp pareado, opcional. Ex: 5521999998888",
    )


# ============================================================
# Webhook (formato Wuzapi)
# ============================================================


class WuzapiWebhookEvent(BaseModel):
    """Payload do webhook Wuzapi.

    O Wuzapi tem um formato meio livre — diferentes versões mandam
    chaves um pouco distintas. Aceitamos os principais e tratamos
    no service.
    """

    model_config = ConfigDict(extra="allow")

    event: str | None = None  # "Message" / "message"
    data: dict[str, Any] | None = None
    instance: str | None = None


__all__ = [
    "AdotarInstanciaRequest",
    "AtualizarWhatsAppUserRequest",
    "CriarWhatsAppUserRequest",
    "InstanciaOut",
    "QRCodeOut",
    "WhatsAppMensagemOut",
    "WhatsAppUserOut",
    "WuzapiWebhookEvent",
]
