"""Cria tabela contratos_hospital (substitui o mock de contratos do front).

Materializa o conceito comercial entre MedPag (BPO) e cada hospital
cliente: mensalidade, taxa por pagamento, % sobre volume, custo
fixo/variável, meta mensal e vigência.

Revision ID: 008_add_contratos_hospital
Revises: 007_add_coordenador_role
Create Date: 2026-05-25 15:30:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "008_add_contratos_hospital"
down_revision: str | None = "007_add_coordenador_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "contratos_hospital" in inspector.get_table_names():
        return

    op.create_table(
        "contratos_hospital",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "cliente_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clientes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Cobrança
        sa.Column(
            "mensalidade_centavos",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "taxa_por_pagamento_centavos",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "percentual_volume_bp",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "volume_medio_mensal_centavos",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        # Custo
        sa.Column(
            "custo_fixo_mensal_centavos",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "custo_variavel_pct",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        # Metas
        sa.Column(
            "meta_mensal_centavos",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        # Vigência
        sa.Column(
            "vigencia_inicio",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        # Status
        sa.Column(
            "ativo", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column("observacoes", sa.String(length=1024), nullable=True),
        # Auditoria
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_contratos_hospital_cliente_id",
        "contratos_hospital",
        ["cliente_id"],
    )
    # Índice parcial: só um contrato ATIVO por cliente
    op.create_index(
        "ix_contratos_hospital_cliente_ativo",
        "contratos_hospital",
        ["cliente_id"],
        unique=True,
        postgresql_where=sa.text("ativo = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_contratos_hospital_cliente_ativo", table_name="contratos_hospital"
    )
    op.drop_index(
        "ix_contratos_hospital_cliente_id", table_name="contratos_hospital"
    )
    op.drop_table("contratos_hospital")
