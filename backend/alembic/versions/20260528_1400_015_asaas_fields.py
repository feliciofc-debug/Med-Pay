"""Adiciona campos de cobranca Asaas em `clientes`.

Persiste o vinculo MedPag <-> Asaas:
    asaas_customer_id      - identificador do customer no Asaas
    asaas_subscription_id  - assinatura ativa
    proximo_vencimento     - data conhecida do proximo boleto/PIX/cobranca
    pagamento_cadastrado   - se cliente ja escolheu meio de pagamento

Migration aditiva, sem downgrade destrutivo (campos sao opcionais).

Revision ID: 015_asaas_fields
Revises: 014_planos_features
Create Date: 2026-05-28 14:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "015_asaas_fields"
down_revision: str | None = "014_planos_features"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clientes",
        sa.Column("asaas_customer_id", sa.String(100), nullable=True),
    )
    op.create_unique_constraint(
        "uq_clientes_asaas_customer", "clientes", ["asaas_customer_id"]
    )
    op.create_index(
        "ix_clientes_asaas_customer_id", "clientes", ["asaas_customer_id"]
    )

    op.add_column(
        "clientes",
        sa.Column("asaas_subscription_id", sa.String(100), nullable=True),
    )
    op.create_unique_constraint(
        "uq_clientes_asaas_subscription",
        "clientes",
        ["asaas_subscription_id"],
    )

    op.add_column(
        "clientes",
        sa.Column("proximo_vencimento", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_clientes_proximo_vencimento", "clientes", ["proximo_vencimento"]
    )

    op.add_column(
        "clientes",
        sa.Column(
            "pagamento_cadastrado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("clientes", "pagamento_cadastrado")
    op.drop_index("ix_clientes_proximo_vencimento", table_name="clientes")
    op.drop_column("clientes", "proximo_vencimento")
    op.drop_constraint(
        "uq_clientes_asaas_subscription", "clientes", type_="unique"
    )
    op.drop_column("clientes", "asaas_subscription_id")
    op.drop_index("ix_clientes_asaas_customer_id", table_name="clientes")
    op.drop_constraint(
        "uq_clientes_asaas_customer", "clientes", type_="unique"
    )
    op.drop_column("clientes", "asaas_customer_id")
