"""Adiciona conta_verificada/conta_invalida_motivo/conta_verificada_em em beneficiarios.

Estrategia de "validacao de conta por aprendizado":
- Nao temos API publica pra validar conta antes de pagar.
- Quando o banco devolve CNAB com erro de conta (codigos 02, 03, AG, AI),
  marcamos a conta deste beneficiario como invalida.
- Proximo lote alerta antes de tentar pagar de novo.

Quando o pagamento e' confirmado pelo banco (codigo 00), marca a conta
como verificada -> nunca mais alerta, mesmo se o beneficiario sair e
voltar pra mesma conta.

IMPORTANTE:
- revision id curto (cabe nos VARCHAR(32) da tabela alembic_version)
- Migration IDEMPOTENTE: usa "ADD COLUMN IF NOT EXISTS" via SQL bruto,
  porque a versao anterior dessa migration (com nome longo) rodou
  parcialmente no Render e ja criou as colunas em alguns ambientes.

Revision ID: 018_benef_conta_verif
Revises: 017_user_cliente_id
Create Date: 2026-05-29 07:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "018_benef_conta_verif"
down_revision: str | None = "017_user_cliente_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Postgres aceita "ADD COLUMN IF NOT EXISTS" desde a versao 9.6.
    # Usamos SQL bruto pra tornar a migration idempotente — protege
    # contra ambientes onde a versao anterior (revision id muito longo
    # = 33 chars) rodou parcialmente, criando as colunas mas falhando
    # ao salvar em alembic_version.
    op.execute(
        "ALTER TABLE beneficiarios "
        "ADD COLUMN IF NOT EXISTS conta_verificada BOOLEAN "
        "NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE beneficiarios "
        "ADD COLUMN IF NOT EXISTS conta_invalida_motivo VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE beneficiarios "
        "ADD COLUMN IF NOT EXISTS conta_verificada_em "
        "TIMESTAMP WITH TIME ZONE"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE beneficiarios DROP COLUMN IF EXISTS conta_verificada_em"
    )
    op.execute(
        "ALTER TABLE beneficiarios DROP COLUMN IF EXISTS conta_invalida_motivo"
    )
    op.execute(
        "ALTER TABLE beneficiarios DROP COLUMN IF EXISTS conta_verificada"
    )
