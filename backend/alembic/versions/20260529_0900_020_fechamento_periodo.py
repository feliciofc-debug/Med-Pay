"""Cria tabela fechamentos_periodo e enum status_fechamento.

Conceito: o gestor do hospital "tranca" um mes operacional, gerando um
snapshot persistido com totais (qtd fichas, qtd medicos, total R$) e
o status do ciclo de vida (ABERTO, TRANCADO, GERADO_LOTE, PAGO).

Revision ID: 020_fechamento_per
Revises: 019_user_roles_hosp
Create Date: 2026-05-29 09:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "020_fechamento_per"
down_revision: str | None = "019_user_roles_hosp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------- ENUM ----------
    status_enum = postgresql.ENUM(
        "ABERTO",
        "TRANCADO",
        "GERADO_LOTE",
        "PAGO",
        name="status_fechamento",
        create_type=False,
    )
    status_enum.create(op.get_bind(), checkfirst=True)

    # ---------- TABELA ----------
    op.create_table(
        "fechamentos_periodo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cliente_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clientes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ano", sa.Integer(), nullable=False),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="status_fechamento", create_type=False),
            nullable=False,
            server_default="TRANCADO",
        ),
        sa.Column(
            "total_centavos",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "qtd_fichas", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "qtd_medicos", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "qtd_linhas", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "lote_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lotes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "trancado_em", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "trancado_por_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reaberto_em", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "reaberto_por_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("observacoes", sa.String(500), nullable=True),
        sa.Column("metadados", postgresql.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "cliente_id", "ano", "mes", name="uq_fechamento_cliente_mes"
        ),
    )
    op.create_index(
        "ix_fechamentos_periodo_cliente_id",
        "fechamentos_periodo",
        ["cliente_id"],
    )
    op.create_index(
        "ix_fechamentos_periodo_status",
        "fechamentos_periodo",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_fechamentos_periodo_status", "fechamentos_periodo")
    op.drop_index(
        "ix_fechamentos_periodo_cliente_id", "fechamentos_periodo"
    )
    op.drop_table("fechamentos_periodo")
    op.execute("DROP TYPE IF EXISTS status_fechamento")
