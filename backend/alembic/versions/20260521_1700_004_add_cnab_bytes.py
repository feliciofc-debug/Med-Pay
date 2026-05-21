"""Persiste conteúdo do CNAB no banco.

O disco do Render é efêmero: a cada deploy os arquivos .rem salvos
em ./storage/cnab somem. Isso fazia o download retornar 404 depois
de qualquer redeploy. Solução: guardar os bytes do CNAB direto na
tabela lotes (e o nome do arquivo gerado).

Revision ID: 004_add_cnab_bytes
Revises: 003_add_modalidade_pagamento
Create Date: 2026-05-21 17:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_add_cnab_bytes"
down_revision: str | None = "003_add_modalidade_pagamento"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lotes",
        sa.Column("nome_arquivo_cnab", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "lotes",
        sa.Column("conteudo_arquivo_cnab", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lotes", "conteudo_arquivo_cnab")
    op.drop_column("lotes", "nome_arquivo_cnab")
