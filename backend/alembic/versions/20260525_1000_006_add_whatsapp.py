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

from alembic import op

revision: str = "006_add_whatsapp"
down_revision: str | None = "005_add_fichas_plantao"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# SQL bruto e idempotente — vide rationale em 005_add_fichas_plantao.
def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE direcao_mensagem AS ENUM ('INBOUND', 'OUTBOUND');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE status_instancia_wpp AS ENUM (
                'DESCONECTADA', 'AGUARDANDO_QR', 'CONECTADA', 'ERRO'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS whatsapp_users (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id                 UUID NOT NULL REFERENCES users(id),
            numero_e164             VARCHAR(20) NOT NULL UNIQUE,
            apelido                 VARCHAR(100),
            pode_aprovar_pagamento  BOOLEAN NOT NULL DEFAULT FALSE,
            ativo                   BOOLEAN NOT NULL DEFAULT TRUE,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_whatsapp_users_user_id "
        "ON whatsapp_users (user_id);"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_whatsapp_users_numero_e164 "
        "ON whatsapp_users (numero_e164);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS whatsapp_mensagens (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            numero_e164         VARCHAR(20) NOT NULL,
            user_id             UUID REFERENCES users(id),
            direcao             direcao_mensagem NOT NULL,
            texto               TEXT NOT NULL,
            wuzapi_message_id   VARCHAR(100) UNIQUE,
            tools_usadas        JSON,
            tokens_prompt       INTEGER NOT NULL DEFAULT 0,
            tokens_resposta     INTEGER NOT NULL DEFAULT 0,
            duracao_ms          INTEGER NOT NULL DEFAULT 0,
            erro                TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_whatsapp_mensagens_numero_e164 "
        "ON whatsapp_mensagens (numero_e164);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_whatsapp_mensagens_user_id "
        "ON whatsapp_mensagens (user_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_whatsapp_mensagens_direcao "
        "ON whatsapp_mensagens (direcao);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_whatsapp_mensagens_created_at "
        "ON whatsapp_mensagens (created_at);"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_whatsapp_mensagens_wuzapi_message_id "
        "ON whatsapp_mensagens (wuzapi_message_id);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS whatsapp_instancias (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            wuzapi_instance_id  VARCHAR(100) NOT NULL UNIQUE,
            wuzapi_token        VARCHAR(255) NOT NULL,
            numero_bot          VARCHAR(20),
            status              status_instancia_wpp NOT NULL DEFAULT 'DESCONECTADA',
            ultimo_qr_base64    TEXT,
            ultimo_qr_at        TIMESTAMPTZ,
            ativa               BOOLEAN NOT NULL DEFAULT TRUE,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS whatsapp_instancias;")
    op.execute("DROP INDEX IF EXISTS ix_whatsapp_mensagens_wuzapi_message_id;")
    op.execute("DROP INDEX IF EXISTS ix_whatsapp_mensagens_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_whatsapp_mensagens_direcao;")
    op.execute("DROP INDEX IF EXISTS ix_whatsapp_mensagens_user_id;")
    op.execute("DROP INDEX IF EXISTS ix_whatsapp_mensagens_numero_e164;")
    op.execute("DROP TABLE IF EXISTS whatsapp_mensagens;")
    op.execute("DROP INDEX IF EXISTS ix_whatsapp_users_numero_e164;")
    op.execute("DROP INDEX IF EXISTS ix_whatsapp_users_user_id;")
    op.execute("DROP TABLE IF EXISTS whatsapp_users;")
    op.execute("DROP TYPE IF EXISTS status_instancia_wpp;")
    op.execute("DROP TYPE IF EXISTS direcao_mensagem;")
