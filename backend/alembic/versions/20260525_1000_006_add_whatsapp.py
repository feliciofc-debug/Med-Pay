"""Adiciona tabelas do módulo Jarvis (WhatsApp + Groq).

Três tabelas:
    - whatsapp_users (whitelist telefone↔user)
    - whatsapp_mensagens (log de todas as conversas)
    - whatsapp_instancias (sessão Wuzapi)

Revision ID: 006_add_whatsapp
Revises: 005_add_fichas_plantao
Create Date: 2026-05-25 10:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_add_whatsapp"
down_revision: str | None = "005_add_fichas_plantao"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DIRECAO = ("INBOUND", "OUTBOUND")
_STATUS_INSTANCIA = ("DESCONECTADA", "AGUARDANDO_QR", "CONECTADA", "ERRO")


def upgrade() -> None:
    direcao_enum = postgresql.ENUM(*_DIRECAO, name="direcao_mensagem", create_type=False)
    direcao_enum.create(op.get_bind(), checkfirst=True)

    status_enum = postgresql.ENUM(
        *_STATUS_INSTANCIA, name="status_instancia_wpp", create_type=False
    )
    status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "whatsapp_users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("numero_e164", sa.String(length=20), nullable=False, unique=True),
        sa.Column("apelido", sa.String(length=100), nullable=True),
        sa.Column(
            "pode_aprovar_pagamento",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "ativo", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_whatsapp_users_user_id", "whatsapp_users", ["user_id"])
    op.create_index(
        "ix_whatsapp_users_numero_e164",
        "whatsapp_users",
        ["numero_e164"],
        unique=True,
    )

    op.create_table(
        "whatsapp_mensagens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("numero_e164", sa.String(length=20), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "direcao",
            sa.Enum(*_DIRECAO, name="direcao_mensagem", create_type=False),
            nullable=False,
        ),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column(
            "wuzapi_message_id", sa.String(length=100), nullable=True, unique=True
        ),
        sa.Column("tools_usadas", postgresql.JSON(), nullable=True),
        sa.Column("tokens_prompt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "tokens_resposta", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("duracao_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_whatsapp_mensagens_numero_e164",
        "whatsapp_mensagens",
        ["numero_e164"],
    )
    op.create_index(
        "ix_whatsapp_mensagens_user_id", "whatsapp_mensagens", ["user_id"]
    )
    op.create_index(
        "ix_whatsapp_mensagens_direcao", "whatsapp_mensagens", ["direcao"]
    )
    op.create_index(
        "ix_whatsapp_mensagens_created_at", "whatsapp_mensagens", ["created_at"]
    )
    op.create_index(
        "ix_whatsapp_mensagens_wuzapi_message_id",
        "whatsapp_mensagens",
        ["wuzapi_message_id"],
        unique=True,
    )

    op.create_table(
        "whatsapp_instancias",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "wuzapi_instance_id", sa.String(length=100), nullable=False, unique=True
        ),
        sa.Column("wuzapi_token", sa.String(length=255), nullable=False),
        sa.Column("numero_bot", sa.String(length=20), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                *_STATUS_INSTANCIA,
                name="status_instancia_wpp",
                create_type=False,
            ),
            nullable=False,
            server_default="DESCONECTADA",
        ),
        sa.Column("ultimo_qr_base64", sa.Text(), nullable=True),
        sa.Column("ultimo_qr_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ativa", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("whatsapp_instancias")

    op.drop_index(
        "ix_whatsapp_mensagens_wuzapi_message_id", table_name="whatsapp_mensagens"
    )
    op.drop_index(
        "ix_whatsapp_mensagens_created_at", table_name="whatsapp_mensagens"
    )
    op.drop_index("ix_whatsapp_mensagens_direcao", table_name="whatsapp_mensagens")
    op.drop_index("ix_whatsapp_mensagens_user_id", table_name="whatsapp_mensagens")
    op.drop_index(
        "ix_whatsapp_mensagens_numero_e164", table_name="whatsapp_mensagens"
    )
    op.drop_table("whatsapp_mensagens")

    op.drop_index("ix_whatsapp_users_numero_e164", table_name="whatsapp_users")
    op.drop_index("ix_whatsapp_users_user_id", table_name="whatsapp_users")
    op.drop_table("whatsapp_users")

    sa.Enum(name="status_instancia_wpp").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="direcao_mensagem").drop(op.get_bind(), checkfirst=True)
