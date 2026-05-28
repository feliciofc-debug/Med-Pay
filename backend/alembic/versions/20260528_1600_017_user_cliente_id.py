"""Adiciona `cliente_id` em `users` pra multi-tenancy.

Users criados antes desta migration ficam com cliente_id = NULL
(considerados "MedPag interno", veem todos os tenants).

A partir desta migration:
    - signup self-service preenche cliente_id automaticamente
    - admin pode criar users de cliente especifico via /api/admin
    - deps require_tenant_filter aplica filtro em queries de lote,
      ficha, pagamento e beneficiario

ON DELETE SET NULL: se o cliente for soft-deletado e depois removido,
o user fica "orfao" como MedPag interno em vez de explodir FK.

Revision ID: 017_user_cliente_id
Revises: 016_config_operacao
Create Date: 2026-05-28 16:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "017_user_cliente_id"
down_revision: str | None = "016_config_operacao"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "cliente_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_users_cliente_id",
        "users",
        "clientes",
        ["cliente_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_cliente_id", "users", ["cliente_id"])


def downgrade() -> None:
    op.drop_index("ix_users_cliente_id", table_name="users")
    op.drop_constraint("fk_users_cliente_id", "users", type_="foreignkey")
    op.drop_column("users", "cliente_id")
