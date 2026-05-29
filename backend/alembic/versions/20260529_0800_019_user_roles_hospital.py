"""Adiciona roles GESTOR, FINANCEIRO e MEDICO ao enum user_role.

Contexto:
A operacao do hospital tem 3 papeis novos alem do COORDENADOR
(que sobe fichas):
  - GESTOR: gestor do hospital, aprova fechamento de periodo
  - FINANCEIRO: financeiro do hospital, baixa CNAB/folha
  - MEDICO: prestador, ve apenas seus proprios plantoes/extrato

Postgres exige usar ALTER TYPE para adicionar valores em ENUMs
existentes (nao da pra fazer com op.alter_column num enum). Por isso
SQL bruto. Idempotente atraves do IF NOT EXISTS (Postgres 11+).

Revision ID: 019_user_roles_hosp
Revises: 018_benef_conta_verif
Create Date: 2026-05-29 08:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "019_user_roles_hosp"
down_revision: str | None = "018_benef_conta_verif"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE deve rodar fora de transacao em Postgres
    # antigos, mas Postgres 12+ aceita dentro de transacao com IF NOT EXISTS.
    # Como o Render esta no 15+, esta tudo bem.
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'GESTOR'")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'FINANCEIRO'")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'MEDICO'")


def downgrade() -> None:
    # Postgres NAO suporta remover valores de um ENUM sem recriar o tipo.
    # Como isso e' destrutivo (afetaria usuarios reais), o downgrade
    # apenas registra a operacao sem desfazer.
    op.execute(
        "-- Downgrade ignorado: Postgres nao suporta DROP VALUE em ENUM. "
        "Para remover, e' necessario recriar o tipo manualmente."
    )
