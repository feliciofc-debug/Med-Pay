"""Schema inicial do MedPag.

Cria todas as tabelas do MVP:
- users
- clientes
- empresa_config
- beneficiarios
- lotes
- pagamentos
- auditoria

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-05-19 06:00:00 UTC
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ====================================================================
    # ENUMs
    # ====================================================================
    user_role = postgresql.ENUM(
        "ADMIN", "APROVADOR", "OPERADOR", name="user_role", create_type=False
    )
    user_role.create(op.get_bind(), checkfirst=True)

    tipo_inscricao = postgresql.ENUM(
        "CPF", "CNPJ", name="tipo_inscricao", create_type=False
    )
    tipo_inscricao.create(op.get_bind(), checkfirst=True)

    status_lote = postgresql.ENUM(
        "RECEBIDO",
        "PROCESSANDO",
        "AGUARDANDO_REVISAO",
        "APROVADO",
        "ENVIADO_BANCO",
        "CONCILIADO",
        "REJEITADO",
        "ERRO",
        name="status_lote",
        create_type=False,
    )
    status_lote.create(op.get_bind(), checkfirst=True)

    status_pagamento = postgresql.ENUM(
        "VALIDO",
        "CORRIGIVEL",
        "BLOQUEADO",
        "APROVADO",
        "REJEITADO",
        "PAGO",
        "NAO_PAGO",
        name="status_pagamento",
        create_type=False,
    )
    status_pagamento.create(op.get_bind(), checkfirst=True)

    # ====================================================================
    # users
    # ====================================================================
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(name="user_role", create_type=False),
            nullable=False,
            server_default="OPERADOR",
        ),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ====================================================================
    # clientes
    # ====================================================================
    op.create_table(
        "clientes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("cnpj", sa.String(14), nullable=True, unique=True),
        sa.Column("email_contato", sa.String(255), nullable=True),
        sa.Column("telefone", sa.String(20), nullable=True),
        sa.Column("observacoes", sa.Text, nullable=True),
        sa.Column("email_remetente_autorizado", sa.String(255), nullable=True),
        sa.Column("mapeamento_colunas", postgresql.JSON, nullable=True),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_clientes_nome", "clientes", ["nome"])
    op.create_index("ix_clientes_cnpj", "clientes", ["cnpj"], unique=True)
    op.create_index(
        "ix_clientes_email_remetente",
        "clientes",
        ["email_remetente_autorizado"],
    )

    # ====================================================================
    # empresa_config (single-tenant no MVP)
    # ====================================================================
    op.create_table(
        "empresa_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("razao_social", sa.String(255), nullable=False),
        sa.Column("nome_fantasia", sa.String(255), nullable=True),
        sa.Column(
            "tipo_inscricao",
            postgresql.ENUM(name="tipo_inscricao", create_type=False),
            nullable=False,
            server_default="CNPJ",
        ),
        sa.Column("cnpj_cpf", sa.String(14), nullable=False, unique=True),
        sa.Column("banco_codigo", sa.String(3), nullable=False, server_default="136"),
        sa.Column("agencia", sa.String(5), nullable=False),
        sa.Column("agencia_dv", sa.String(1), nullable=True),
        sa.Column("conta_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("conta_dv", sa.String(1), nullable=False),
        sa.Column("conta_mascarada", sa.String(20), nullable=False),
        sa.Column("codigo_convenio", sa.String(20), nullable=False),
        sa.Column("endereco_logradouro", sa.String(30), nullable=False),
        sa.Column("endereco_numero", sa.String(5), nullable=False),
        sa.Column("endereco_complemento", sa.String(15), nullable=True),
        sa.Column("endereco_cidade", sa.String(20), nullable=False),
        sa.Column("endereco_cep", sa.String(8), nullable=False),
        sa.Column("endereco_uf", sa.String(2), nullable=False),
        sa.Column(
            "proximo_numero_sequencial",
            sa.Integer,
            nullable=False,
            server_default="1",
        ),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ====================================================================
    # beneficiarios
    # ====================================================================
    op.create_table(
        "beneficiarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cpf_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("cpf_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("cpf_mascarado", sa.String(20), nullable=False),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("banco_codigo", sa.String(3), nullable=True),
        sa.Column("agencia_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("conta_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("conta_mascarada", sa.String(20), nullable=True),
        sa.Column("pix_chave_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("pix_tipo", sa.String(20), nullable=True),
        sa.Column(
            "total_pagamentos", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "valor_medio_centavos", sa.BigInteger, nullable=False, server_default="0"
        ),
        sa.Column(
            "valor_min_centavos", sa.BigInteger, nullable=False, server_default="0"
        ),
        sa.Column(
            "valor_max_centavos", sa.BigInteger, nullable=False, server_default="0"
        ),
        sa.Column("ultimo_pagamento_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_beneficiarios_cpf_hash", "beneficiarios", ["cpf_hash"], unique=True
    )
    op.create_index("ix_beneficiarios_nome", "beneficiarios", ["nome"])

    # ====================================================================
    # lotes
    # ====================================================================
    op.create_table(
        "lotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cliente_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clientes.id"),
            nullable=False,
        ),
        sa.Column("nome_arquivo", sa.String(500), nullable=False),
        sa.Column("hash_conteudo", sa.String(64), nullable=False, unique=True),
        sa.Column("referencia", sa.String(100), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="status_lote", create_type=False),
            nullable=False,
            server_default="RECEBIDO",
        ),
        sa.Column(
            "total_pagamentos", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "total_validos", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "total_corrigiveis", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "total_bloqueados", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "valor_total_centavos",
            sa.BigInteger,
            nullable=False,
            server_default="0",
        ),
        sa.Column("caminho_arquivo_original", sa.String(500), nullable=True),
        sa.Column("caminho_arquivo_cnab", sa.String(500), nullable=True),
        sa.Column("hash_arquivo_cnab", sa.String(64), nullable=True),
        sa.Column("caminho_arquivo_retorno", sa.String(500), nullable=True),
        sa.Column(
            "aprovado_por_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("aprovado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observacoes_aprovacao", sa.Text, nullable=True),
        sa.Column("mensagem_erro", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_lotes_cliente_id", "lotes", ["cliente_id"])
    op.create_index("ix_lotes_hash_conteudo", "lotes", ["hash_conteudo"], unique=True)
    op.create_index("ix_lotes_status", "lotes", ["status"])

    # ====================================================================
    # pagamentos
    # ====================================================================
    op.create_table(
        "pagamentos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "lote_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lotes.id"),
            nullable=False,
        ),
        sa.Column(
            "beneficiario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("beneficiarios.id"),
            nullable=True,
        ),
        sa.Column("linha_planilha", sa.Integer, nullable=False),
        sa.Column("cpf_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("cpf_hash", sa.String(64), nullable=False),
        sa.Column("cpf_mascarado", sa.String(20), nullable=False),
        sa.Column("cpf_original", sa.String(50), nullable=True),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("banco_codigo", sa.String(3), nullable=True),
        sa.Column("agencia_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("conta_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("conta_mascarada", sa.String(20), nullable=True),
        sa.Column("valor_centavos", sa.BigInteger, nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="status_pagamento", create_type=False),
            nullable=False,
            server_default="BLOQUEADO",
        ),
        sa.Column("codigos_erro", sa.Text, nullable=True),
        sa.Column("mensagens_validacao", sa.Text, nullable=True),
        sa.Column("cpf_sugerido", sa.String(20), nullable=True),
        sa.Column("retorno_codigo", sa.String(10), nullable=True),
        sa.Column("retorno_descricao", sa.String(500), nullable=True),
        sa.Column("pago_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_pagamentos_lote_id", "pagamentos", ["lote_id"])
    op.create_index(
        "ix_pagamentos_beneficiario_id", "pagamentos", ["beneficiario_id"]
    )
    op.create_index("ix_pagamentos_cpf_hash", "pagamentos", ["cpf_hash"])
    op.create_index("ix_pagamentos_status", "pagamentos", ["status"])

    # ====================================================================
    # auditoria
    # ====================================================================
    op.create_table(
        "auditoria",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("acao", sa.String(100), nullable=False),
        sa.Column("entidade_tipo", sa.String(50), nullable=True),
        sa.Column("entidade_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("detalhes", postgresql.JSON, nullable=True),
        sa.Column("hash_relacionado", sa.String(64), nullable=True),
        sa.Column("ip_address", postgresql.INET, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("mensagem", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_auditoria_user_id", "auditoria", ["user_id"])
    op.create_index("ix_auditoria_acao", "auditoria", ["acao"])
    op.create_index("ix_auditoria_entidade_tipo", "auditoria", ["entidade_tipo"])
    op.create_index("ix_auditoria_entidade_id", "auditoria", ["entidade_id"])
    op.create_index("ix_auditoria_hash_relacionado", "auditoria", ["hash_relacionado"])
    op.create_index("ix_auditoria_created_at", "auditoria", ["created_at"])


def downgrade() -> None:
    op.drop_table("auditoria")
    op.drop_table("pagamentos")
    op.drop_table("lotes")
    op.drop_table("beneficiarios")
    op.drop_table("empresa_config")
    op.drop_table("clientes")
    op.drop_table("users")

    sa.Enum(name="status_pagamento").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="status_lote").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tipo_inscricao").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
