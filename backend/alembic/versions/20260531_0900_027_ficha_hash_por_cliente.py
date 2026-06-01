"""Duplicata de ficha passa a ser por (cliente, hash), não global.

Antes, hash_arquivo era UNIQUE global — o mesmo arquivo enviado em qualquer
tenant/login bloqueava todos os outros. Agora a unicidade é por hospital:
o mesmo PDF/foto pode ser enviado em clientes/tenants diferentes, mas
continua barrado dentro do MESMO cliente (evita pagamento em duplicidade).

Remove a constraint/índice únicos globais e cria:
  - índice NÃO-único em hash_arquivo (lookups)
  - unique composta (cliente_id, hash_arquivo) = uq_ficha_cliente_hash

SQL bruto e idempotente.

Revision ID: 027_ficha_hash_por_cliente
Revises: 026_aportes_hospital
Create Date: 2026-05-31 09:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "027_ficha_hash_por_cliente"
down_revision: str | None = "026_aportes_hospital"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) Remove a constraint UNIQUE inline (auto-nomeada pelo Postgres) e o
    #    índice único global, se existirem.
    op.execute(
        "ALTER TABLE fichas_plantao "
        "DROP CONSTRAINT IF EXISTS fichas_plantao_hash_arquivo_key;"
    )
    op.execute("DROP INDEX IF EXISTS ix_fichas_plantao_hash_arquivo;")

    # 2) Recria o índice de busca como NÃO-único.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fichas_plantao_hash_arquivo "
        "ON fichas_plantao (hash_arquivo);"
    )

    # 3) Unicidade composta por cliente + arquivo.
    #    Postgres não tem "ADD CONSTRAINT IF NOT EXISTS"; em vez de DO/EXCEPTION
    #    (que tinha sintaxe inválida e derrubava o deploy), checamos o catálogo
    #    e só criamos se ainda não existir. Idempotente e sem pegadinha de
    #    PL/pgSQL.
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS ("
        "SELECT 1 FROM pg_constraint WHERE conname = 'uq_ficha_cliente_hash'"
        ") THEN "
        "ALTER TABLE fichas_plantao "
        "ADD CONSTRAINT uq_ficha_cliente_hash UNIQUE (cliente_id, hash_arquivo); "
        "END IF; "
        "END $$;"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE fichas_plantao "
        "DROP CONSTRAINT IF EXISTS uq_ficha_cliente_hash;"
    )
    op.execute("DROP INDEX IF EXISTS ix_fichas_plantao_hash_arquivo;")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_fichas_plantao_hash_arquivo "
        "ON fichas_plantao (hash_arquivo);"
    )
