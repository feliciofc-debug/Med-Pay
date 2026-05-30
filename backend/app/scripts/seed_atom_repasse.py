"""Provisiona o tenant da operação de repasse da Atom (laboratório SCP).

Ideia (decisão do Felício): a operação de repasse NÃO roda no login
god-mode `expo@atombrasildigital.com` (MedPag interno, que vê todos os
menus). Ela roda num tenant dedicado — tipo MEDPAG_REPASSE, modo
REPASSE_SCP — com um login próprio. Esse login enxerga SÓ o que um
cliente de repasse veria, então serve de bancada de teste/validação do
feature-gating ao mesmo tempo que é a operação real.

O que cria/garante (idempotente + self-healing):
    1. Cliente "Atom Repasse" aplicando o preset MEDPAG_REPASSE
       (tipo + modo_pagamento + features SCP/lucro ligadas).
    2. Usuário GESTOR amarrado a esse cliente (vê só o tenant Atom).

Credenciais por env (não commitamos segredo):
    ATOM_EMAIL   (default repasse@atombrasildigital.com)
    ATOM_SENHA   (default de laboratório — TROQUE em produção)
    ATOM_NOME    (default "Atom Repasse")
    ATOM_CNPJ    (opcional)

Uso:
    python -m app.scripts.seed_atom_repasse

No Render: roda no boot quando SEED_ATOM=true, ou via job one-off.
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.cliente import Cliente, ModoPagamento, TipoCliente
from app.models.user import User, UserRole
from app.services.auth import AuthService
from app.services.presets_negocio import get_preset

CLIENTE_NOME_PADRAO = "Atom Repasse"
EMAIL_PADRAO = "repasse@atombrasildigital.com"
SENHA_PADRAO = "atom-repasse-2026"  # laboratório — troque em produção
NOME_LOGIN_PADRAO = "Atom Repasse (Operação)"


async def _provisionar_cliente() -> Cliente:
    """Cria/atualiza o cliente Atom aplicando o preset MEDPAG_REPASSE."""
    nome = os.environ.get("ATOM_NOME", CLIENTE_NOME_PADRAO).strip()
    cnpj = (os.environ.get("ATOM_CNPJ") or "").strip() or None
    preset = get_preset(TipoCliente.MEDPAG_REPASSE)

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(Cliente).where(Cliente.nome == nome))
        cliente = existing.scalar_one_or_none()

        if cliente is None:
            cliente = Cliente(
                nome=nome,
                cnpj=cnpj,
                email_contato=os.environ.get("ATOM_EMAIL", EMAIL_PADRAO).strip(),
                observacoes=(
                    "Tenant da operação de repasse SCP da Atom. Laboratório de "
                    "teste/validação do feature-gating (modelo MEDPAG_REPASSE)."
                ),
                tipo=preset.tipo,
                modo_pagamento=preset.modo_pagamento,
                features_override=dict(preset.features),
                ativo=True,
            )
            db.add(cliente)
            await db.flush()
            print(f"[+] Cliente criado: {nome} (id={cliente.id})")
        else:
            # self-healing: realinha com o preset (sem apagar overrides extras)
            cliente.tipo = preset.tipo
            cliente.modo_pagamento = preset.modo_pagamento
            merged = {**(cliente.features_override or {}), **preset.features}
            cliente.features_override = merged
            print(f"[=] Cliente já existe, realinhado ao preset: {nome} (id={cliente.id})")

        await db.commit()
        await db.refresh(cliente)
        return cliente


async def _provisionar_login(cliente_id) -> None:
    """Cria/garante o login GESTOR amarrado ao tenant Atom."""
    email = os.environ.get("ATOM_EMAIL", EMAIL_PADRAO).lower().strip()
    nome = os.environ.get("ATOM_NOME_LOGIN", NOME_LOGIN_PADRAO).strip()
    senha = os.environ.get("ATOM_SENHA", SENHA_PADRAO).strip()

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == email))
        user = existing.scalar_one_or_none()

        if user is None:
            service = AuthService(db)
            user = await service.criar_usuario(
                email=email,
                nome=nome,
                senha=senha,
                role=UserRole.GESTOR,
            )
            user.cliente_id = cliente_id
            await db.commit()
            print(f"[+] Login criado: {email} (role=GESTOR, cliente={cliente_id})")
            if senha == SENHA_PADRAO:
                print(f"    Senha de laboratório: {senha}")
                print("    [!] Defina ATOM_SENHA e troque em produção.")
        else:
            # self-healing: garante o vínculo com o tenant (não mexe na senha)
            if user.cliente_id != cliente_id:
                user.cliente_id = cliente_id
                await db.commit()
                print(f"[=] Login já existia — vínculo com tenant Atom ajustado: {email}")
            else:
                print(f"[=] Login já existe e vinculado: {email}")


async def main() -> None:
    print("=" * 60)
    print("MedPag — Provisionamento do tenant Atom Repasse (SCP)")
    print("=" * 60)

    cliente = await _provisionar_cliente()
    await _provisionar_login(cliente.id)

    print("=" * 60)
    print("[OK] Atom Repasse provisionado")
    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
