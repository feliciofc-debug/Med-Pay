"""Adiciona tabela fichas_plantao para o módulo de OCR.

Coordenadores de hospital sobem a ficha carimbada (foto/PDF). O OCR
extrai os plantões e o aprovador converte em lote de pagamento.
Bytes do arquivo ficam na própria tabela (Render tem disco efêmero).

Revision ID: 005_add_fichas_plantao
Revises: 004_add_cnab_bytes
Create Date: 2026-05-25 09:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "005_add_fichas_plantao"
down_revision: str | None = "004_add_cnab_bytes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# SQL bruto e idempotente. Usar `sa.Enum` com `create_type=False` em
# alembic/SQLAlchemy 2.x ainda dispara `before_create` em alguns paths,
# o que faz o CREATE TYPE rodar mesmo quando o type já existe órfão de
# uma execução anterior. Com SQL bruto + IF NOT EXISTS / DO $$ a migration
# fica 100% idempotente, independente do estado em que o banco esteja.
def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE status_ficha AS ENUM (
                'RECEBIDA', 'PROCESSANDO', 'EXTRAIDA',
                'REVISADA', 'CONVERTIDA', 'ERRO'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fichas_plantao (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            cliente_id      UUID NOT NULL REFERENCES clientes(id),
            nome_arquivo    VARCHAR(500) NOT NULL,
            mime_type       VARCHAR(100) NOT NULL,
            tamanho_bytes   INTEGER NOT NULL DEFAULT 0,
            arquivo_bytes   BYTEA NOT NULL,
            hash_arquivo    VARCHAR(64) NOT NULL UNIQUE,
            status          status_ficha NOT NULL DEFAULT 'RECEBIDA',
            texto_ocr       TEXT,
            paginas_ocr     INTEGER NOT NULL DEFAULT 0,
            linhas_extraidas JSON,
            metadados       JSON,
            mensagem_erro   TEXT,
            enviado_por_id  UUID REFERENCES users(id),
            revisado_por_id UUID REFERENCES users(id),
            revisado_at     TIMESTAMPTZ,
            lote_gerado_id  UUID REFERENCES lotes(id),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fichas_plantao_cliente_id "
        "ON fichas_plantao (cliente_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fichas_plantao_status "
        "ON fichas_plantao (status);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fichas_plantao_enviado_por_id "
        "ON fichas_plantao (enviado_por_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fichas_plantao_lote_gerado_id "
        "ON fichas_plantao (lote_gerado_id);"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_fichas_plantao_hash_arquivo "
        "ON fichas_plantao (hash_arquivo);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_fichas_plantao_hash_arquivo;")
    op.execute("DROP INDEX IF EXISTS ix_fichas_plantao_lote_gerado_id;")
    op.execute("DROP INDEX IF EXISTS ix_fichas_plantao_enviado_por_id;")
    op.execute("DROP INDEX IF EXISTS ix_fichas_plantao_status;")
    op.execute("DROP INDEX IF EXISTS ix_fichas_plantao_cliente_id;")
    op.execute("DROP TABLE IF EXISTS fichas_plantao;")
    op.execute("DROP TYPE IF EXISTS status_ficha;")
