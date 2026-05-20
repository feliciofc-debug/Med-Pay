"""Popula o banco com dados de demonstração.

Cria:
- 2 clientes (Hospital Santa Casa, Clínica Vida Nova)
- 1 usuário aprovador adicional (Thiago) — caso ADMIN tenha sido criado com outro email

Idempotente: rodar várias vezes não duplica nada. Cada criação verifica
se o registro já existe antes de inserir.

Uso (dentro do container backend ou .venv ativado):
    python -m app.scripts.seed_demo

No deploy do Render: roda automaticamente no startup quando SEED_DEMO=true.
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.cliente import Cliente
from app.models.user import User, UserRole
from app.services.auth import AuthService


CLIENTES_DEMO = [
    {
        "nome": "Hospital Santa Casa de Misericórdia",
        "cnpj": "11222333000181",
        "email_contato": "financeiro@santacasa.demo",
        "telefone": "(11) 3500-1000",
        "email_remetente_autorizado": "financeiro@santacasa.demo",
        "observacoes": (
            "Hospital geral com 280 leitos. Folha de repasse mensal "
            "para médicos plantonistas. Cliente demonstração."
        ),
    },
    {
        "nome": "Clínica Vida Nova",
        "cnpj": "44555666000172",
        "email_contato": "contato@vidanova.demo",
        "telefone": "(11) 4200-5000",
        "email_remetente_autorizado": "contato@vidanova.demo",
        "observacoes": (
            "Clínica especializada em cardiologia e imagem. "
            "Folha mensal menor (20-30 médicos). Cliente demonstração."
        ),
    },
]


USUARIO_THIAGO = {
    "email": "thiago@medpag.com.br",
    "nome": "Thiago",
    "senha_padrao": "thiago123",  # apenas se ADMIN_SENHA não foi definido
    "role": UserRole.APROVADOR,
}


async def _criar_clientes() -> None:
    """Cria clientes de demonstração se ainda não existirem."""
    async with AsyncSessionLocal() as db:
        for dados in CLIENTES_DEMO:
            existing = await db.execute(
                select(Cliente).where(Cliente.cnpj == dados["cnpj"])
            )
            if existing.scalar_one_or_none() is not None:
                print(f"[=] Cliente já existe: {dados['nome']}")
                continue

            cliente = Cliente(
                nome=dados["nome"],
                cnpj=dados["cnpj"],
                email_contato=dados["email_contato"],
                telefone=dados["telefone"],
                email_remetente_autorizado=dados["email_remetente_autorizado"],
                observacoes=dados["observacoes"],
                ativo=True,
            )
            db.add(cliente)
            await db.flush()
            print(f"[+] Cliente criado: {dados['nome']} (id={cliente.id})")

        await db.commit()


async def _criar_usuario_thiago() -> None:
    """Cria usuário Thiago como APROVADOR (se ainda não existir).

    Lê senha de THIAGO_SENHA ou usa senha-padrão. Sempre imprime no log
    em qual caso estamos, pra ficar claro pro Felício/Thiago.
    """
    senha = os.environ.get("THIAGO_SENHA", USUARIO_THIAGO["senha_padrao"]).strip()  # type: ignore[arg-type]
    email = USUARIO_THIAGO["email"]
    assert isinstance(email, str)

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none() is not None:
            print(f"[=] Usuário já existe: {email}")
            return

        service = AuthService(db)
        user = await service.criar_usuario(
            email=email,
            nome=USUARIO_THIAGO["nome"],  # type: ignore[arg-type]
            senha=senha,
            role=USUARIO_THIAGO["role"],  # type: ignore[arg-type]
        )
        await db.commit()
        print(f"[+] Usuário criado: {email} (id={user.id}, role={user.role.value})")
        if senha == USUARIO_THIAGO["senha_padrao"]:
            print(f"    Senha padrão de demonstração: {senha}")
            print("    [!] Troque na primeira oportunidade em produção.")


async def main() -> None:
    print("=" * 60)
    print("MedPag — Seed de Demonstração")
    print("=" * 60)

    await _criar_clientes()
    await _criar_usuario_thiago()

    print("=" * 60)
    print("[OK] Seed concluído")
    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
