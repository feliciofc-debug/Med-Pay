"""Adiciona Pagamento.modalidade e Pagamento.chave_pix.

Espelha o template Unicred do Thiago, onde cada pagamento é PIX OU TED
(nunca os dois). Necessário pro gerador CNAB 240 saber em qual lote
(tipo_servico + forma_lanc) cada pagamento entra.

Default = TED (forma mais conservadora; sempre funciona, mesmo sem
chave PIX cadastrada).

Revision ID: 003_add_modalidade_pagamento
Revises: 002_add_enviado_por_lote
Create Date: 2026-05-20 19:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_add_modalidade_pagamento"
down_revision: str | None = "002_add_enviado_por_lote"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Cria o ENUM no Postgres
    modalidade_enum = sa.Enum(
        "PIX",
        "TED",
        "TRANSF_UNICRED",
        name="modalidade_pagamento",
    )
    modalidade_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "pagamentos",
        sa.Column(
            "modalidade",
            modalidade_enum,
            nullable=False,
            server_default="TED",
        ),
    )
    op.create_index(
        "ix_pagamentos_modalidade", "pagamentos", ["modalidade"], unique=False
    )

    op.add_column(
        "pagamentos",
        sa.Column("chave_pix", sa.String(length=77), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pagamentos", "chave_pix")
    op.drop_index("ix_pagamentos_modalidade", table_name="pagamentos")
    op.drop_column("pagamentos", "modalidade")

    modalidade_enum = sa.Enum(name="modalidade_pagamento")
    modalidade_enum.drop(op.get_bind(), checkfirst=True)
