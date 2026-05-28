"""Adiciona configuracao operacional per-tenant em `clientes`.

Campos novos pra a tela Configurar Operacao:
    dia_fechamento      - dia do mes do fechamento (1-31, 0=ultimo util)
    fuso_horario        - timezone IANA (default America/Sao_Paulo)
    modalidade_preferida - hint pra novos lancamentos (PIX/TED/CC)
    logo_url            - url do logo do cliente
    cor_primaria        - cor de branding (#hex)

Migration aditiva. Sem downgrade destrutivo.

Revision ID: 016_config_operacao
Revises: 015_asaas_fields
Create Date: 2026-05-28 15:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "016_config_operacao"
down_revision: str | None = "015_asaas_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clientes",
        sa.Column(
            "dia_fechamento",
            sa.Integer(),
            nullable=False,
            server_default="25",
        ),
    )
    op.add_column(
        "clientes",
        sa.Column(
            "fuso_horario",
            sa.String(50),
            nullable=False,
            server_default="America/Sao_Paulo",
        ),
    )
    op.add_column(
        "clientes",
        sa.Column(
            "modalidade_preferida",
            sa.String(20),
            nullable=False,
            server_default="PIX",
        ),
    )
    op.add_column(
        "clientes",
        sa.Column("logo_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "clientes",
        sa.Column(
            "cor_primaria",
            sa.String(7),
            nullable=False,
            server_default="#2D5F3F",
        ),
    )


def downgrade() -> None:
    op.drop_column("clientes", "cor_primaria")
    op.drop_column("clientes", "logo_url")
    op.drop_column("clientes", "modalidade_preferida")
    op.drop_column("clientes", "fuso_horario")
    op.drop_column("clientes", "dia_fechamento")
