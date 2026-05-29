"""Memoria persistente do Jarvis + flag de relatorio diario proativo.

Adiciona:
- Tabela jarvis_memorias (fatos, preferencias, decisoes, notas por user)
- whatsapp_users.receber_relatorio_diario (opt-in pro Jarvis mandar
  diagnostico todo dia 8h)

Revision ID: 022_jarvis_mem
Revises: 021_user_benef_id
Create Date: 2026-05-29 15:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "022_jarvis_mem"
down_revision: str | None = "021_user_benef_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enum tipo_memoria_jarvis
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE tipo_memoria_jarvis AS ENUM "
        "('PREFERENCIA','FATO','DECISAO','NOTA'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    # Tabela jarvis_memorias (idempotente)
    op.execute(
        "CREATE TABLE IF NOT EXISTS jarvis_memorias ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "tipo tipo_memoria_jarvis NOT NULL DEFAULT 'NOTA', "
        "conteudo TEXT NOT NULL, "
        "tags VARCHAR(255), "
        "relevancia INTEGER NOT NULL DEFAULT 5, "
        "ativa BOOLEAN NOT NULL DEFAULT TRUE, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_jarvis_memorias_user_id "
        "ON jarvis_memorias(user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_jarvis_memorias_tipo "
        "ON jarvis_memorias(tipo)"
    )

    # Flag de relatorio diario em whatsapp_users
    op.execute(
        "ALTER TABLE whatsapp_users "
        "ADD COLUMN IF NOT EXISTS receber_relatorio_diario "
        "BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE whatsapp_users "
        "DROP COLUMN IF EXISTS receber_relatorio_diario"
    )
    op.execute("DROP TABLE IF EXISTS jarvis_memorias")
    op.execute("DROP TYPE IF EXISTS tipo_memoria_jarvis")
