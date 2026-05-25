"""Adiciona valor COORDENADOR ao enum user_role.

O coordenador é o funcionário interno (da empresa de repasse, ex.: time
do Thiago) que carrega as fichas/planilhas dos hospitais para a
plataforma. Ele tem visão restrita:

- Sobe ficha (OCR) e planilha
- Vê APENAS as submissões que ele mesmo fez
- Tem extrato de banco de horas pra não duplicar a mesma ficha
- NÃO aprova lotes, NÃO vê Executivo, NÃO gerencia usuários

Migration idempotente: usa ALTER TYPE ... ADD VALUE IF NOT EXISTS.

Revision ID: 007_add_coordenador_role
Revises: 006_add_whatsapp
Create Date: 2026-05-25 15:00:00 UTC
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "007_add_coordenador_role"
down_revision: str | None = "006_add_whatsapp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Adiciona COORDENADOR ao enum existente.

    Postgres não permite ALTER TYPE dentro de uma transação por padrão
    em versões antigas, mas o Alembic já roda cada migration em sua
    própria transação. ADD VALUE IF NOT EXISTS é idempotente.
    """
    # COMMIT da transação corrente antes (Postgres < 12 exigia, 12+
    # aceita dentro de transação se não for usado na mesma tx).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'COORDENADOR'")


def downgrade() -> None:
    """Remoção de valor de enum em Postgres é não-trivial.

    Requer recriar o tipo. Não fazemos automaticamente — se precisar
    reverter, tem que migrar usuários COORDENADOR pra outro role
    primeiro e depois aplicar manualmente.
    """
    # No-op intencional. Em ambiente de produção, COORDENADOR já pode
    # ter usuários atribuídos — remover o valor quebraria o banco.
    pass
