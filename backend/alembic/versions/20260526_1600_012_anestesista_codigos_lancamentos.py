"""Cria tabelas `codigos_servico` e `lancamentos_servico` (caso anestesista).

Habilita o fluxo de autoatendimento por CRM:
    - Médico (Beneficiario) entra com CRM
    - Digita data + código do serviço
    - Sistema consulta `codigos_servico` (escopo por cliente_id)
    - Cria `LancamentoServico` ligado ao Beneficiario

Sem mudanças destrutivas. Idempotente para suportar redeploy.

Revision ID: 012_anestesista_codigos_lancamentos
Revises: 011_beneficiario_cadastro_mestre
Create Date: 2026-05-26 16:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "012_anestesista_codigos_lancamentos"
down_revision: str | None = "011_beneficiario_cadastro_mestre"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ----- ENUM status_lancamento_servico -----
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE status_lancamento_servico AS ENUM (
                'LANCADO', 'CONFERIDO', 'INCLUIDO_EM_LOTE', 'PAGO', 'CANCELADO'
            );
        EXCEPTION WHEN duplicate_object THEN null; END $$;
        """
    )

    # ----- codigos_servico -----
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS codigos_servico (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            cliente_id      UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
            codigo          VARCHAR(40) NOT NULL,
            descricao       VARCHAR(500) NOT NULL,
            valor_centavos  BIGINT NOT NULL DEFAULT 0,
            categoria       VARCHAR(120),
            porte           VARCHAR(40),
            ativo           BOOLEAN NOT NULL DEFAULT TRUE,
            observacoes     VARCHAR(1024),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_codigo_servico_cliente_codigo UNIQUE (cliente_id, codigo)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_codigos_servico_cliente_id "
        "ON codigos_servico (cliente_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_codigos_servico_codigo "
        "ON codigos_servico (codigo);"
    )

    # ----- lancamentos_servico -----
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lancamentos_servico (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            cliente_id          UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
            beneficiario_id     UUID NOT NULL REFERENCES beneficiarios(id) ON DELETE RESTRICT,
            codigo_servico_id   UUID NOT NULL REFERENCES codigos_servico(id) ON DELETE RESTRICT,
            data_servico        DATE NOT NULL,
            codigo_snapshot     VARCHAR(40) NOT NULL,
            descricao_snapshot  VARCHAR(500) NOT NULL,
            valor_centavos      BIGINT NOT NULL,
            hospital_local      VARCHAR(255),
            paciente_iniciais   VARCHAR(10),
            observacoes         VARCHAR(1024),
            status              status_lancamento_servico NOT NULL DEFAULT 'LANCADO',
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lancamentos_servico_cliente_id "
        "ON lancamentos_servico (cliente_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lancamentos_servico_beneficiario_id "
        "ON lancamentos_servico (beneficiario_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lancamentos_servico_codigo_servico_id "
        "ON lancamentos_servico (codigo_servico_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lancamentos_servico_data_servico "
        "ON lancamentos_servico (data_servico);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lancamentos_servico_status "
        "ON lancamentos_servico (status);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lancamentos_servico CASCADE;")
    op.execute("DROP TABLE IF EXISTS codigos_servico CASCADE;")
    op.execute("DROP TYPE IF EXISTS status_lancamento_servico;")
