"""Cria tabela `planos` e adiciona campos de plano/features em `clientes`.

Estabelece a fundação SaaS:
    - `planos`: 4 seeds (Inicial / Profissional / Avançado / Enterprise)
    - `clientes.plano_id`: FK pro plano vigente
    - `clientes.features_override`: JSONB com overrides pontuais
    - `clientes.status_assinatura`: enum (TRIAL/ATIVO/INADIMPLENTE/SUSPENSO/CANCELADO)
    - `clientes.trial_termina_em`: timestamp do fim do trial

Clientes existentes ficam em ATIVO sem plano vinculado (legados podem
ser migrados manualmente depois pela tela de admin).

Revision ID: 014_planos_features
Revises: 013_modulo_vital
Create Date: 2026-05-28 11:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "014_planos_features"
down_revision: str | None = "013_modulo_vital"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ============================================================
# Seeds — 4 planos comerciais
# ============================================================

_SEEDS_PLANOS = [
    {
        "slug": "inicial",
        "nome": "Inicial",
        "descricao": (
            "Plano de entrada self-service. 30 dias de trial gratuito. "
            "Ideal pra clínicas e hospitais pequenos começarem sozinhos."
        ),
        "preco_mensal_centavos": 49900,  # R$ 499,00
        "trial_dias": 30,
        "publico": True,
        "ordem": 1,
        "features": {
            "pagamento.cnab": True,
            "pagamento.folha_municipal": False,
            "pagamento.pix_direto": False,
            "pagamento.bolo_do_dia": False,
            "modulo.whatsapp_jarvis": False,
            "modulo.sentinela_vital": False,
            "modulo.equipe_flex": False,
            "modulo.crm_medico": False,
            "modulo.antifraude_qr": False,
            "modulo.dashboard_executivo": False,
            "modulo.contratos_hospital": False,
            "limite.pagamentos_mes": 200,
            "limite.usuarios": 3,
            "limite.clientes_filhos": 0,
        },
    },
    {
        "slug": "profissional",
        "nome": "Profissional",
        "descricao": (
            "Operação assistida (BPO Essencial). MedPag opera junto. "
            "Inclui WhatsApp e Equipe Flex. Sem trial — contratual."
        ),
        "preco_mensal_centavos": 199900,  # R$ 1.999,00
        "trial_dias": 0,
        "publico": False,
        "ordem": 2,
        "features": {
            "pagamento.cnab": True,
            "pagamento.folha_municipal": False,
            "pagamento.pix_direto": False,
            "pagamento.bolo_do_dia": True,
            "modulo.whatsapp_jarvis": True,
            "modulo.sentinela_vital": False,
            "modulo.equipe_flex": True,
            "modulo.crm_medico": True,
            "modulo.antifraude_qr": False,
            "modulo.dashboard_executivo": True,
            "modulo.contratos_hospital": True,
            "limite.pagamentos_mes": 2000,
            "limite.usuarios": 15,
            "limite.clientes_filhos": 3,
        },
    },
    {
        "slug": "avancado",
        "nome": "Avançado",
        "descricao": (
            "BPO Premium. Todas as features comerciais ligadas. "
            "Sentinela e antifraude QR já liberados. Sem trial."
        ),
        "preco_mensal_centavos": 499900,  # R$ 4.999,00
        "trial_dias": 0,
        "publico": False,
        "ordem": 3,
        "features": {
            "pagamento.cnab": True,
            "pagamento.folha_municipal": False,
            "pagamento.pix_direto": True,
            "pagamento.bolo_do_dia": True,
            "modulo.whatsapp_jarvis": True,
            "modulo.sentinela_vital": True,
            "modulo.equipe_flex": True,
            "modulo.crm_medico": True,
            "modulo.antifraude_qr": True,
            "modulo.dashboard_executivo": True,
            "modulo.contratos_hospital": True,
            "limite.pagamentos_mes": 10000,
            "limite.usuarios": 50,
            "limite.clientes_filhos": 10,
        },
    },
    {
        "slug": "enterprise",
        "nome": "Enterprise",
        "descricao": (
            "Customizado. Integração com folha (municipal, eSocial, API). "
            "SLA dedicado. Preço sob negociação. Ideal pra prefeituras e "
            "redes hospitalares grandes."
        ),
        "preco_mensal_centavos": 0,  # sob demanda
        "trial_dias": 0,
        "publico": False,
        "ordem": 4,
        "features": {
            "pagamento.cnab": True,
            "pagamento.folha_municipal": True,
            "pagamento.pix_direto": True,
            "pagamento.bolo_do_dia": True,
            "modulo.whatsapp_jarvis": True,
            "modulo.sentinela_vital": True,
            "modulo.equipe_flex": True,
            "modulo.crm_medico": True,
            "modulo.antifraude_qr": True,
            "modulo.dashboard_executivo": True,
            "modulo.contratos_hospital": True,
            # ilimitados representados como None
            "limite.pagamentos_mes": None,
            "limite.usuarios": None,
            "limite.clientes_filhos": None,
        },
    },
]


def upgrade() -> None:
    # ---------- Enum status_assinatura ----------
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE status_assinatura AS ENUM (
                'TRIAL', 'ATIVO', 'INADIMPLENTE', 'SUSPENSO', 'CANCELADO'
            );
        EXCEPTION WHEN duplicate_object THEN null; END $$;
        """
    )

    # ---------- Tabela planos ----------
    op.create_table(
        "planos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(40), nullable=False, unique=True),
        sa.Column("nome", sa.String(80), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("preco_mensal_centavos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trial_dias", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("features", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("publico", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_planos_slug", "planos", ["slug"], unique=True)

    # ---------- Campos novos em clientes ----------
    op.add_column(
        "clientes",
        sa.Column("plano_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_clientes_plano",
        "clientes",
        "planos",
        ["plano_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_clientes_plano_id", "clientes", ["plano_id"])

    op.add_column(
        "clientes",
        sa.Column(
            "features_override",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "clientes",
        sa.Column(
            "status_assinatura",
            sa.Enum(
                "TRIAL",
                "ATIVO",
                "INADIMPLENTE",
                "SUSPENSO",
                "CANCELADO",
                name="status_assinatura",
                create_type=False,
            ),
            nullable=False,
            server_default="ATIVO",
        ),
    )
    op.create_index("ix_clientes_status_assinatura", "clientes", ["status_assinatura"])

    op.add_column(
        "clientes",
        sa.Column("trial_termina_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_clientes_trial_termina_em", "clientes", ["trial_termina_em"])

    # ---------- Seeds ----------
    planos_table = sa.table(
        "planos",
        sa.column("slug", sa.String),
        sa.column("nome", sa.String),
        sa.column("descricao", sa.Text),
        sa.column("preco_mensal_centavos", sa.Integer),
        sa.column("trial_dias", sa.Integer),
        sa.column("features", JSONB),
        sa.column("publico", sa.Boolean),
        sa.column("ordem", sa.Integer),
    )
    op.bulk_insert(planos_table, _SEEDS_PLANOS)


def downgrade() -> None:
    op.drop_index("ix_clientes_trial_termina_em", table_name="clientes")
    op.drop_column("clientes", "trial_termina_em")

    op.drop_index("ix_clientes_status_assinatura", table_name="clientes")
    op.drop_column("clientes", "status_assinatura")

    op.drop_column("clientes", "features_override")

    op.drop_index("ix_clientes_plano_id", table_name="clientes")
    op.drop_constraint("fk_clientes_plano", "clientes", type_="foreignkey")
    op.drop_column("clientes", "plano_id")

    op.drop_index("ix_planos_slug", table_name="planos")
    op.drop_table("planos")

    op.execute("DROP TYPE IF EXISTS status_assinatura;")
