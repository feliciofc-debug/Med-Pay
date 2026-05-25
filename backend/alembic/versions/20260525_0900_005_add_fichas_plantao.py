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

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "005_add_fichas_plantao"
down_revision: str | None = "004_add_cnab_bytes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_STATUS_FICHA = ("RECEBIDA", "PROCESSANDO", "EXTRAIDA", "REVISADA", "CONVERTIDA", "ERRO")


def upgrade() -> None:
    # Cria o ENUM de forma idempotente. Se uma execução anterior falhou
    # parcialmente (criou o type mas não a tabela), checkfirst do SQLAlchemy
    # nem sempre detecta. SQL bruto é a forma mais confiável.
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

    inspector = inspect(op.get_bind())
    if "fichas_plantao" in inspector.get_table_names():
        # Tabela já existe (execução anterior chegou até aqui).
        # Pula tudo — idempotência total.
        return

    op.create_table(
        "fichas_plantao",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "cliente_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clientes.id"),
            nullable=False,
        ),
        sa.Column("nome_arquivo", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("tamanho_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("arquivo_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("hash_arquivo", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "status",
            sa.Enum(*_STATUS_FICHA, name="status_ficha", create_type=False),
            nullable=False,
            server_default="RECEBIDA",
        ),
        sa.Column("texto_ocr", sa.Text(), nullable=True),
        sa.Column("paginas_ocr", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("linhas_extraidas", postgresql.JSON(), nullable=True),
        sa.Column("metadados", postgresql.JSON(), nullable=True),
        sa.Column("mensagem_erro", sa.Text(), nullable=True),
        sa.Column(
            "enviado_por_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "revisado_por_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("revisado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "lote_gerado_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lotes.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_fichas_plantao_cliente_id", "fichas_plantao", ["cliente_id"]
    )
    op.create_index("ix_fichas_plantao_status", "fichas_plantao", ["status"])
    op.create_index(
        "ix_fichas_plantao_enviado_por_id", "fichas_plantao", ["enviado_por_id"]
    )
    op.create_index(
        "ix_fichas_plantao_lote_gerado_id", "fichas_plantao", ["lote_gerado_id"]
    )
    op.create_index(
        "ix_fichas_plantao_hash_arquivo",
        "fichas_plantao",
        ["hash_arquivo"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_fichas_plantao_hash_arquivo", table_name="fichas_plantao")
    op.drop_index("ix_fichas_plantao_lote_gerado_id", table_name="fichas_plantao")
    op.drop_index("ix_fichas_plantao_enviado_por_id", table_name="fichas_plantao")
    op.drop_index("ix_fichas_plantao_status", table_name="fichas_plantao")
    op.drop_index("ix_fichas_plantao_cliente_id", table_name="fichas_plantao")
    op.drop_table("fichas_plantao")
    sa.Enum(name="status_ficha").drop(op.get_bind(), checkfirst=True)
