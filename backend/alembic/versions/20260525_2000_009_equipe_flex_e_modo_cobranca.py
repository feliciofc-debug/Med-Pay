"""Equipe Flex (banco de horas compartilhado) + Modo de Cobrança no contrato.

Cria as 3 tabelas do módulo Equipe Flex:
    - equipes_flex (cabeçalho)
    - membros_equipe (médicos/profissionais)
    - fechamentos_equipe (snapshot mensal que vira lote)

E adiciona o enum modo_cobranca_hospital + coluna modo_cobranca em
contratos_hospital, para diferenciar:
    - PERCENTUAL_REPASSE (privado, MedPag desconta % do bruto)
    - MENSALIDADE_SAAS (público, MedPag cobra fixo, 100% vai pros médicos)

SQL bruto e idempotente para sobreviver a deploys parciais.

Revision ID: 009_equipe_flex
Revises: 008_add_contratos_hospital
Create Date: 2026-05-25 20:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "009_equipe_flex"
down_revision: str | None = "008_add_contratos_hospital"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------- ENUM modo_cobranca_hospital (idempotente) ----------
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE modo_cobranca_hospital AS ENUM (
                'PERCENTUAL_REPASSE', 'MENSALIDADE_SAAS'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    # ---------- Coluna modo_cobranca em contratos_hospital ----------
    op.execute(
        """
        ALTER TABLE contratos_hospital
        ADD COLUMN IF NOT EXISTS modo_cobranca modo_cobranca_hospital
            NOT NULL DEFAULT 'PERCENTUAL_REPASSE';
        """
    )

    # ---------- Tabela equipes_flex ----------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equipes_flex (
            id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            cliente_id             UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
            nome                   VARCHAR(120) NOT NULL,
            categoria              VARCHAR(80) NOT NULL DEFAULT 'Plantonista',
            valor_hora_centavos    INTEGER NOT NULL DEFAULT 0,
            ativa                  BOOLEAN NOT NULL DEFAULT TRUE,
            observacoes            VARCHAR(1024),
            created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_equipes_flex_cliente_id "
        "ON equipes_flex (cliente_id);"
    )

    # ---------- Tabela membros_equipe ----------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS membros_equipe (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            equipe_id           UUID NOT NULL REFERENCES equipes_flex(id) ON DELETE CASCADE,
            nome                VARCHAR(200) NOT NULL,
            cpf                 VARCHAR(11) NOT NULL,
            crm_ou_registro     VARCHAR(40),
            chave_pix           VARCHAR(120),
            banco_codigo        VARCHAR(3),
            agencia             VARCHAR(10),
            conta               VARCHAR(20),
            ativo               BOOLEAN NOT NULL DEFAULT TRUE,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_membro_equipe_cpf UNIQUE (equipe_id, cpf)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_membros_equipe_equipe_id "
        "ON membros_equipe (equipe_id);"
    )

    # ---------- Tabela fechamentos_equipe ----------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fechamentos_equipe (
            id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            equipe_id                   UUID NOT NULL REFERENCES equipes_flex(id) ON DELETE CASCADE,
            competencia                 VARCHAR(7) NOT NULL,
            horas_total                 INTEGER NOT NULL,
            valor_hora_centavos         INTEGER NOT NULL,
            valor_bruto_centavos        INTEGER NOT NULL,
            desconto_medpag_centavos    INTEGER NOT NULL DEFAULT 0,
            valor_liquido_centavos      INTEGER NOT NULL,
            qtd_membros                 INTEGER NOT NULL,
            valor_por_membro_centavos   INTEGER NOT NULL,
            origem                      VARCHAR(20) NOT NULL DEFAULT 'DIGITACAO',
            ficha_id                    UUID REFERENCES fichas_plantao(id) ON DELETE SET NULL,
            lote_id                     UUID REFERENCES lotes(id) ON DELETE SET NULL,
            aprovado_por_id             UUID REFERENCES users(id) ON DELETE SET NULL,
            aprovado_at                 TIMESTAMPTZ,
            observacoes                 VARCHAR(1024),
            created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_fechamento_equipe_competencia UNIQUE (equipe_id, competencia)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fechamentos_equipe_equipe_id "
        "ON fechamentos_equipe (equipe_id);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_fechamentos_equipe_equipe_id;")
    op.execute("DROP TABLE IF EXISTS fechamentos_equipe;")
    op.execute("DROP INDEX IF EXISTS ix_membros_equipe_equipe_id;")
    op.execute("DROP TABLE IF EXISTS membros_equipe;")
    op.execute("DROP INDEX IF EXISTS ix_equipes_flex_cliente_id;")
    op.execute("DROP TABLE IF EXISTS equipes_flex;")
    op.execute(
        "ALTER TABLE contratos_hospital DROP COLUMN IF EXISTS modo_cobranca;"
    )
    op.execute("DROP TYPE IF EXISTS modo_cobranca_hospital;")
