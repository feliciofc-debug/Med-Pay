"""Reseta a senha de um usuário (uso administrativo / emergencial).

Lê as variáveis de ambiente:
    ADMIN_EMAIL    (obrigatório) — email do usuário a resetar
    ADMIN_SENHA    (obrigatório) — nova senha

Cria o usuário se não existir (como ADMIN), ou atualiza a senha se já existir.

Uso (dentro do Render Shell ou container backend):
    python -m app.scripts.reset_senha

Segurança:
- Mensagens nunca exibem a senha em claro
- Não é exposto via API
- Audita a alteração no stdout (timestamp + usuário)
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole


async def main() -> None:
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    nome = os.environ.get("ADMIN_NOME", "Administrador").strip()
    senha = os.environ.get("ADMIN_SENHA", "").strip()

    if not email:
        print("ERRO: variável ADMIN_EMAIL não definida.")
        sys.exit(1)
    if not senha:
        print("ERRO: variável ADMIN_SENHA não definida.")
        sys.exit(1)
    if len(senha) < 6:
        print("ERRO: senha precisa ter pelo menos 6 caracteres.")
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        agora = datetime.now(UTC).isoformat()

        if user is None:
            user = User(
                email=email,
                nome=nome,
                hashed_password=hash_password(senha),
                role=UserRole.ADMIN,
                ativo=True,
            )
            db.add(user)
            await db.commit()
            print("=" * 60)
            print("[OK] Usuário CRIADO")
            print(f"  Email: {email}")
            print(f"  Nome:  {nome}")
            print(f"  Role:  ADMIN")
            print(f"  Senha: (definida, não exibida)")
            print(f"  Quando: {agora}")
            print("=" * 60)
        else:
            user.hashed_password = hash_password(senha)
            user.ativo = True  # garante que não está desativado
            await db.commit()
            print("=" * 60)
            print("[OK] Senha ATUALIZADA")
            print(f"  Email: {email}")
            print(f"  Nome:  {user.nome}")
            print(f"  Role:  {user.role.value}")
            print(f"  Ativo: {user.ativo}")
            print(f"  Quando: {agora}")
            print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
