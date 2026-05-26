"""Adiciona banco_emissor em empresa_config (CNAB Itaú + Bradesco).

Enum novo banco_emissor_cnab com 3 valores: UNICRED, ITAU, BRADESCO.
Coluna `banco_emissor` em empresa_config com default UNICRED para
preservar compatibilidade com instâncias já em produção.

SQL bruto idempotente — sobrevive a deploy parcial.

Revision ID: 010_banco_emissor_cnab
Revises: 009_equipe_flex
Create Date: 2026-05-26 09:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "010_banco_emissor_cnab"
down_revision: str | None = "009_equipe_flex"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE banco_emissor_cnab AS ENUM (
                'UNICRED', 'ITAU', 'BRADESCO'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    op.execute(
        """
        ALTER TABLE empresa_config
        ADD COLUMN IF NOT EXISTS banco_emissor banco_emissor_cnab
            NOT NULL DEFAULT 'UNICRED';
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE empresa_config DROP COLUMN IF EXISTS banco_emissor;"
    )
    op.execute("DROP TYPE IF EXISTS banco_emissor_cnab;")
