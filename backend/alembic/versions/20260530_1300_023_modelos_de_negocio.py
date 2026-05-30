"""Engenharia de modelos de negócio: tipo de tenant + modo de pagamento + hierarquia.

Materializa os 3 eixos da arquitetura discutida:
- Eixo 1 (QUEM): clientes.tipo  -> enum tipo_cliente
- Eixo 3 (COMO): clientes.modo_pagamento -> enum modo_pagamento_cliente
- Hierarquia: clientes.cliente_pai_id (empresa de repasse -> hospitais filhos)

O Eixo 2 (O QUE / capacidades) reaproveita o sistema de features já
existente (Plano.features + Cliente.features_override) — sem schema novo.

Defaults preservam o comportamento atual: todo cliente legado vira
HOSPITAL + CNAB_BANCARIO, sem precisar de backfill.

SQL bruto e idempotente pra sobreviver a deploys parciais.

Revision ID: 023_modelos_negocio
Revises: 022_jarvis_mem
Create Date: 2026-05-30 13:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "023_modelos_negocio"
down_revision: str | None = "022_jarvis_mem"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------- Enum tipo_cliente (Eixo 1) ----------
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE tipo_cliente AS ENUM "
        "('HOSPITAL','EMPRESA_REPASSE','MEDPAG_REPASSE','ONG'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    # ---------- Enum modo_pagamento_cliente (Eixo 3) ----------
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE modo_pagamento_cliente AS ENUM "
        "('CNAB_BANCARIO','EXPORT_RH','REPASSE_SCP','SOMENTE_GESTAO'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    # ---------- Colunas em clientes ----------
    op.execute(
        "ALTER TABLE clientes "
        "ADD COLUMN IF NOT EXISTS tipo tipo_cliente "
        "NOT NULL DEFAULT 'HOSPITAL'"
    )
    op.execute(
        "ALTER TABLE clientes "
        "ADD COLUMN IF NOT EXISTS modo_pagamento modo_pagamento_cliente "
        "NOT NULL DEFAULT 'CNAB_BANCARIO'"
    )
    op.execute(
        "ALTER TABLE clientes "
        "ADD COLUMN IF NOT EXISTS cliente_pai_id UUID "
        "REFERENCES clientes(id) ON DELETE SET NULL"
    )

    # ---------- Índices ----------
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clientes_tipo ON clientes(tipo)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clientes_cliente_pai_id "
        "ON clientes(cliente_pai_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_clientes_cliente_pai_id")
    op.execute("DROP INDEX IF EXISTS ix_clientes_tipo")
    op.execute("ALTER TABLE clientes DROP COLUMN IF EXISTS cliente_pai_id")
    op.execute("ALTER TABLE clientes DROP COLUMN IF EXISTS modo_pagamento")
    op.execute("ALTER TABLE clientes DROP COLUMN IF EXISTS tipo")
    op.execute("DROP TYPE IF EXISTS modo_pagamento_cliente")
    op.execute("DROP TYPE IF EXISTS tipo_cliente")
