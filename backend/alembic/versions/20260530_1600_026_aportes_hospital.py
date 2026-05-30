"""Aportes recebidos por hospital da carteira (libera a distribuição).

Cria a tabela aportes_hospital + enum status_aporte. Rastreia os depósitos
que cada hospital faz na conta da empresa de repasse antes do pagamento.

SQL bruto e idempotente.

Revision ID: 026_aportes_hospital
Revises: 025_contas_repasse
Create Date: 2026-05-30 16:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "026_aportes_hospital"
down_revision: str | None = "025_contas_repasse"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE status_aporte AS ENUM ('PENDENTE','CONFIRMADO'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS aportes_hospital (
            id UUID PRIMARY KEY,
            cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
            conta_pagadora_id UUID REFERENCES empresa_config(id) ON DELETE SET NULL,
            lote_id UUID REFERENCES lotes(id) ON DELETE SET NULL,
            valor_centavos BIGINT NOT NULL,
            data_recebimento DATE NOT NULL,
            competencia VARCHAR(7),
            referencia VARCHAR(255),
            status status_aporte NOT NULL DEFAULT 'PENDENTE',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_aportes_hospital_cliente_id "
        "ON aportes_hospital(cliente_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_aportes_hospital_status "
        "ON aportes_hospital(status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_aportes_hospital_conta "
        "ON aportes_hospital(conta_pagadora_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_aportes_hospital_lote "
        "ON aportes_hospital(lote_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS aportes_hospital")
    op.execute("DROP TYPE IF EXISTS status_aporte")
