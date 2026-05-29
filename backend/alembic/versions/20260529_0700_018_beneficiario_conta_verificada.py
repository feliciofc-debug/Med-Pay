"""Adiciona `conta_verificada`, `conta_invalida_motivo`, `conta_verificada_em` em beneficiarios.

Estrategia de "validacao de conta por aprendizado":
- Nao temos API publica pra validar conta antes de pagar.
- Quando o banco devolve CNAB com erro de conta (codigos 02, 03, AG, AI),
  marcamos a conta deste beneficiario como invalida.
- Proximo lote alerta antes de tentar pagar de novo.

Quando o pagamento e' confirmado pelo banco (codigo 00), marca a conta
como verificada -> nunca mais alerta, mesmo se o beneficiario sair e
voltar pra mesma conta.

Revision ID: 018_beneficiario_conta_verificada
Revises: 017_user_cliente_id
Create Date: 2026-05-29 07:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "018_beneficiario_conta_verificada"
down_revision: str | None = "017_user_cliente_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "beneficiarios",
        sa.Column(
            "conta_verificada",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "beneficiarios",
        sa.Column(
            "conta_invalida_motivo",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "beneficiarios",
        sa.Column(
            "conta_verificada_em",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("beneficiarios", "conta_verificada_em")
    op.drop_column("beneficiarios", "conta_invalida_motivo")
    op.drop_column("beneficiarios", "conta_verificada")
