"""Adiciona users.beneficiario_id (vinculo MEDICO -> cadastro de prestador).

Quando o User tem role=MEDICO, este id aponta para o Beneficiario que
representa o cadastro dele como prestador no hospital. Permite ao app
do medico filtrar plantoes/extrato pelo proprio CPF sem expor o numero.

Revision ID: 021_user_benef_id
Revises: 020_fechamento_per
Create Date: 2026-05-29 10:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "021_user_benef_id"
down_revision: str | None = "020_fechamento_per"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS beneficiario_id UUID "
        "REFERENCES beneficiarios(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_users_beneficiario_id "
        "ON users(beneficiario_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_beneficiario_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS beneficiario_id")
