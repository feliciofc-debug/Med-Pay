"""Contas de Repasse multi-banco: empresa_config deixa de ser singleton.

- empresa_config ganha cliente_id (dono da conta), apelido e modo_execucao
  (CNAB hoje / API futuro). Remove o UNIQUE de cnpj_cpf (o mesmo CNPJ pode
  ter várias contas/bancos).
- clientes ganha conta_pagadora_id (qual conta executa os pagamentos dele).

Compat: a conta existente fica com cliente_id NULL (legada/global) e o
resolver de conta cai nela por padrão — o CNAB que já roda não muda.

SQL bruto e idempotente.

Revision ID: 025_contas_repasse
Revises: 024_scp
Create Date: 2026-05-30 15:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "025_contas_repasse"
down_revision: str | None = "024_scp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------- Enum modo_execucao_conta ----------
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE modo_execucao_conta AS ENUM ('CNAB','API'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    # ---------- Colunas em empresa_config ----------
    op.execute(
        "ALTER TABLE empresa_config "
        "ADD COLUMN IF NOT EXISTS cliente_id UUID "
        "REFERENCES clientes(id) ON DELETE CASCADE"
    )
    op.execute("ALTER TABLE empresa_config ADD COLUMN IF NOT EXISTS apelido VARCHAR(80)")
    op.execute(
        "ALTER TABLE empresa_config "
        "ADD COLUMN IF NOT EXISTS modo_execucao modo_execucao_conta "
        "NOT NULL DEFAULT 'CNAB'"
    )

    # cnpj_cpf deixa de ser único (mesmo CNPJ, vários bancos)
    op.execute(
        "ALTER TABLE empresa_config DROP CONSTRAINT IF EXISTS empresa_config_cnpj_cpf_key"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_empresa_config_cnpj_cpf "
        "ON empresa_config(cnpj_cpf)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_empresa_config_cliente_id "
        "ON empresa_config(cliente_id)"
    )

    # ---------- Vínculo do cliente com a conta pagadora ----------
    op.execute(
        "ALTER TABLE clientes "
        "ADD COLUMN IF NOT EXISTS conta_pagadora_id UUID "
        "REFERENCES empresa_config(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clientes_conta_pagadora_id "
        "ON clientes(conta_pagadora_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_clientes_conta_pagadora_id")
    op.execute("ALTER TABLE clientes DROP COLUMN IF EXISTS conta_pagadora_id")
    op.execute("DROP INDEX IF EXISTS ix_empresa_config_cliente_id")
    op.execute("DROP INDEX IF EXISTS ix_empresa_config_cnpj_cpf")
    op.execute("ALTER TABLE empresa_config DROP COLUMN IF EXISTS modo_execucao")
    op.execute("ALTER TABLE empresa_config DROP COLUMN IF EXISTS apelido")
    op.execute("ALTER TABLE empresa_config DROP COLUMN IF EXISTS cliente_id")
    op.execute("DROP TYPE IF EXISTS modo_execucao_conta")
