"""Refatora `beneficiarios` em cadastro mestre por hospital.

Mudanças:
    - Adiciona cliente_id (FK clientes, ON DELETE CASCADE)
    - Adiciona status (PENDENTE/ATIVO/INATIVO)
    - Adiciona origem_cadastro (PLANILHA/MANUAL/FICHA_OCR/LOTE/SEED)
    - Adiciona crm, categoria, especialidade, email, telefone
    - Adiciona valor_padrao_centavos (BIGINT)
    - Adiciona observacoes
    - Adiciona agencia_mascarada, pix_chave_mascarada
    - Troca UNIQUE(cpf_hash) por UNIQUE(cliente_id, cpf_hash)
    - Adiciona beneficiario_id em membros_equipe (FK opcional)

Estratégia: como `beneficiarios` ainda não é populado no fluxo principal
(o lookup por CPF não foi cabeado), TRUNCATE no upgrade é seguro. Se em
algum ambiente houver linhas antigas (testes manuais), elas são
descartadas — não há perda de informação útil.

SQL bruto idempotente. Sobrevive a deploy parcial.

Revision ID: 011_beneficiario_cadastro_mestre
Revises: 010_banco_emissor_cnab
Create Date: 2026-05-26 11:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "011_beneficiario_cadastro_mestre"
down_revision: str | None = "010_banco_emissor_cnab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Limpa qualquer linha residual — beneficiarios ainda não era usado no
    # fluxo principal e os FK pra beneficiarios em pagamentos é nullable.
    # Quebrar a referência por SET NULL via UPDATE evita FK violation.
    op.execute("UPDATE pagamentos SET beneficiario_id = NULL;")
    op.execute("DELETE FROM beneficiarios;")

    # ----- ENUMs -----
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE status_beneficiario AS ENUM (
                'PENDENTE', 'ATIVO', 'INATIVO'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE origem_cadastro_beneficiario AS ENUM (
                'PLANILHA', 'MANUAL', 'FICHA_OCR', 'LOTE', 'SEED'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    # ----- Drop UNIQUE antigo de cpf_hash (se existir) -----
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE beneficiarios DROP CONSTRAINT IF EXISTS beneficiarios_cpf_hash_key;
        EXCEPTION WHEN others THEN null;
        END $$;
        """
    )
    # Em algumas versões do alembic o nome do constraint pode variar:
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE beneficiarios DROP CONSTRAINT IF EXISTS uq_beneficiarios_cpf_hash;
        EXCEPTION WHEN others THEN null;
        END $$;
        """
    )

    # ----- Novas colunas -----
    op.execute(
        """
        ALTER TABLE beneficiarios
            ADD COLUMN IF NOT EXISTS cliente_id UUID,
            ADD COLUMN IF NOT EXISTS crm VARCHAR(40),
            ADD COLUMN IF NOT EXISTS categoria VARCHAR(80),
            ADD COLUMN IF NOT EXISTS especialidade VARCHAR(80),
            ADD COLUMN IF NOT EXISTS email VARCHAR(255),
            ADD COLUMN IF NOT EXISTS telefone VARCHAR(20),
            ADD COLUMN IF NOT EXISTS agencia_mascarada VARCHAR(20),
            ADD COLUMN IF NOT EXISTS pix_chave_mascarada VARCHAR(120),
            ADD COLUMN IF NOT EXISTS valor_padrao_centavos BIGINT,
            ADD COLUMN IF NOT EXISTS status status_beneficiario
                NOT NULL DEFAULT 'ATIVO',
            ADD COLUMN IF NOT EXISTS origem_cadastro origem_cadastro_beneficiario
                NOT NULL DEFAULT 'MANUAL',
            ADD COLUMN IF NOT EXISTS observacoes VARCHAR(1024);
        """
    )

    # cliente_id: garante NOT NULL agora que tabela está vazia
    op.execute(
        """
        ALTER TABLE beneficiarios
            ALTER COLUMN cliente_id SET NOT NULL;
        """
    )

    # FK pra clientes (com cascade)
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE beneficiarios
                ADD CONSTRAINT fk_beneficiarios_cliente
                FOREIGN KEY (cliente_id)
                REFERENCES clientes (id)
                ON DELETE CASCADE;
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    # Index do cliente_id
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_beneficiarios_cliente_id "
        "ON beneficiarios (cliente_id);"
    )

    # UNIQUE composto (cliente_id, cpf_hash)
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE beneficiarios
                ADD CONSTRAINT uq_beneficiario_cliente_cpf
                UNIQUE (cliente_id, cpf_hash);
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    # ----- MembroEquipe.beneficiario_id -----
    op.execute(
        """
        ALTER TABLE membros_equipe
            ADD COLUMN IF NOT EXISTS beneficiario_id UUID;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE membros_equipe
                ADD CONSTRAINT fk_membros_equipe_beneficiario
                FOREIGN KEY (beneficiario_id)
                REFERENCES beneficiarios (id)
                ON DELETE SET NULL;
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_membros_equipe_beneficiario_id "
        "ON membros_equipe (beneficiario_id);"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE membros_equipe "
        "DROP CONSTRAINT IF EXISTS fk_membros_equipe_beneficiario;"
    )
    op.execute("DROP INDEX IF EXISTS ix_membros_equipe_beneficiario_id;")
    op.execute(
        "ALTER TABLE membros_equipe "
        "DROP COLUMN IF EXISTS beneficiario_id;"
    )

    op.execute(
        "ALTER TABLE beneficiarios "
        "DROP CONSTRAINT IF EXISTS uq_beneficiario_cliente_cpf;"
    )
    op.execute("DROP INDEX IF EXISTS ix_beneficiarios_cliente_id;")
    op.execute(
        "ALTER TABLE beneficiarios "
        "DROP CONSTRAINT IF EXISTS fk_beneficiarios_cliente;"
    )
    op.execute(
        """
        ALTER TABLE beneficiarios
            DROP COLUMN IF EXISTS cliente_id,
            DROP COLUMN IF EXISTS crm,
            DROP COLUMN IF EXISTS categoria,
            DROP COLUMN IF EXISTS especialidade,
            DROP COLUMN IF EXISTS email,
            DROP COLUMN IF EXISTS telefone,
            DROP COLUMN IF EXISTS agencia_mascarada,
            DROP COLUMN IF EXISTS pix_chave_mascarada,
            DROP COLUMN IF EXISTS valor_padrao_centavos,
            DROP COLUMN IF EXISTS status,
            DROP COLUMN IF EXISTS origem_cadastro,
            DROP COLUMN IF EXISTS observacoes;
        """
    )
    op.execute("DROP TYPE IF EXISTS status_beneficiario;")
    op.execute("DROP TYPE IF EXISTS origem_cadastro_beneficiario;")
