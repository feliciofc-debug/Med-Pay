"""Cria o usuário ADMIN inicial do sistema.

Uso (dentro do container backend):
    python -m app.scripts.create_admin

Lê as variáveis de ambiente:
    ADMIN_EMAIL    (default: admin@medpag.local)
    ADMIN_NOME     (default: Administrador)
    ADMIN_SENHA    (default: gera senha aleatória e imprime)

Em produção, exporte ADMIN_SENHA com uma senha forte ANTES de rodar.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.user import User, UserRole
from app.services.auth import AuthService


async def main() -> None:
    email = os.environ.get("ADMIN_EMAIL", "admin@medpag.local").strip().lower()
    nome = os.environ.get("ADMIN_NOME", "Administrador").strip()
    senha = os.environ.get("ADMIN_SENHA", "").strip()

    senha_gerada: str | None = None
    if not senha:
        senha = secrets.token_urlsafe(16)
        senha_gerada = senha

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none() is not None:
            print(f"[!] Já existe usuário com email {email}. Nada a fazer.")
            return

        service = AuthService(db)
        user = await service.criar_usuario(
            email=email,
            nome=nome,
            senha=senha,
            role=UserRole.ADMIN,
        )
        await db.commit()

        print("=" * 60)
        print("[OK] Usuário ADMIN criado com sucesso")
        print("=" * 60)
        print(f"  ID:    {user.id}")
        print(f"  Email: {user.email}")
        print(f"  Nome:  {user.nome}")
        print(f"  Role:  {user.role.value}")
        if senha_gerada:
            print(f"  Senha (gerada): {senha_gerada}")
            print()
            print(
                "[!] ANOTE A SENHA AGORA. Ela não será exibida novamente. "
                "Em produção use ADMIN_SENHA via ambiente."
            )
        print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
