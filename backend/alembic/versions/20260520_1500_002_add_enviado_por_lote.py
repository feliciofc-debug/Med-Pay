"""Adiciona Lote.enviado_por_id — rastreia operador que subiu a planilha.

Crítico para o relatório de erros por operador: hoje só sabemos quem
aprovou, mas o erro de digitação/consolidação vem de quem subiu, não
de quem aprovou. Operadores são treinados com base nesse relatório.

Revision ID: 002_add_enviado_por_lote
Revises: 001_initial_schema
Create Date: 2026-05-20 15:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_add_enviado_por_lote"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lotes",
        sa.Column(
            "enviado_por_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_lotes_enviado_por_id", "lotes", ["enviado_por_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_lotes_enviado_por_id", table_name="lotes")
    op.drop_column("lotes", "enviado_por_id")
