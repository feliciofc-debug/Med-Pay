"""Sociedade em Conta de Participação (SCP): participantes, apurações, distribuições.

Tabelas do modelo de negócio MEDPAG_REPASSE (SCP), onde a MedPag é sócia
ostensiva e os médicos são participantes que recebem distribuição de
resultado (não pagamento por serviço).

- scp_participantes  : médico ↔ SCP + regra de cota
- scp_apuracoes      : fechamento de período (receita − custos = resultado)
- scp_distribuicoes  : quanto cada participante recebe na apuração

SQL bruto e idempotente.

Revision ID: 024_scp
Revises: 023_modelos_negocio
Create Date: 2026-05-30 13:30:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "024_scp"
down_revision: str | None = "023_modelos_negocio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------- Enums ----------
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE regra_cota_scp AS ENUM "
        "('PERCENTUAL_FIXO','PROPORCIONAL_SERVICO','POR_APORTE'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE status_apuracao_scp AS ENUM "
        "('ABERTA','FECHADA','DISTRIBUIDA'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    # ---------- scp_participantes ----------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scp_participantes (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            cliente_id       UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
            beneficiario_id  UUID NOT NULL REFERENCES beneficiarios(id) ON DELETE CASCADE,
            regra_cota       regra_cota_scp NOT NULL DEFAULT 'PROPORCIONAL_SERVICO',
            percentual_bp    INTEGER NOT NULL DEFAULT 0,
            aporte_centavos  BIGINT NOT NULL DEFAULT 0,
            vigencia_inicio  DATE NOT NULL DEFAULT CURRENT_DATE,
            vigencia_fim     DATE,
            ativo            BOOLEAN NOT NULL DEFAULT TRUE,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_scp_participante UNIQUE (cliente_id, beneficiario_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scp_participantes_cliente_id "
        "ON scp_participantes(cliente_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scp_participantes_beneficiario_id "
        "ON scp_participantes(beneficiario_id)"
    )

    # ---------- scp_apuracoes ----------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scp_apuracoes (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            cliente_id              UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
            competencia             VARCHAR(7) NOT NULL,
            receita_bruta_centavos  BIGINT NOT NULL DEFAULT 0,
            custos_centavos         BIGINT NOT NULL DEFAULT 0,
            resultado_centavos      BIGINT NOT NULL DEFAULT 0,
            status                  status_apuracao_scp NOT NULL DEFAULT 'ABERTA',
            lote_id                 UUID REFERENCES lotes(id) ON DELETE SET NULL,
            observacoes             VARCHAR(1024),
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_scp_apuracao_competencia UNIQUE (cliente_id, competencia)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scp_apuracoes_cliente_id "
        "ON scp_apuracoes(cliente_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scp_apuracoes_competencia "
        "ON scp_apuracoes(competencia)"
    )

    # ---------- scp_distribuicoes ----------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scp_distribuicoes (
            id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            apuracao_id              UUID NOT NULL REFERENCES scp_apuracoes(id) ON DELETE CASCADE,
            participante_id          UUID NOT NULL REFERENCES scp_participantes(id) ON DELETE CASCADE,
            beneficiario_id          UUID NOT NULL REFERENCES beneficiarios(id) ON DELETE CASCADE,
            base_centavos            BIGINT NOT NULL DEFAULT 0,
            percentual_aplicado_bp   INTEGER NOT NULL DEFAULT 0,
            valor_centavos           BIGINT NOT NULL DEFAULT 0,
            created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scp_distribuicoes_apuracao_id "
        "ON scp_distribuicoes(apuracao_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scp_distribuicoes_participante_id "
        "ON scp_distribuicoes(participante_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scp_distribuicoes_beneficiario_id "
        "ON scp_distribuicoes(beneficiario_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scp_distribuicoes")
    op.execute("DROP TABLE IF EXISTS scp_apuracoes")
    op.execute("DROP TABLE IF EXISTS scp_participantes")
    op.execute("DROP TYPE IF EXISTS status_apuracao_scp")
    op.execute("DROP TYPE IF EXISTS regra_cota_scp")
