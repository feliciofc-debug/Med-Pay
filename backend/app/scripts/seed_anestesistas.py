"""Seed do fluxo anestesista (caso Sandro).

Cria:
    - 1 cliente "Operação Sandro Anestesistas"
    - 10 códigos de serviço de exemplo (até a planilha real chegar)
    - 5 médicos anestesistas (Beneficiarios) com CRM para testar o login

Idempotente: rodar de novo não duplica nada.

Uso:
    python -m app.scripts.seed_anestesistas
"""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

from sqlalchemy import select

from app.core.crypto import encrypt, hash_for_lookup, mask_cpf
from app.core.database import AsyncSessionLocal
from app.models.beneficiario import (
    Beneficiario,
    OrigemCadastroBeneficiario,
    StatusBeneficiario,
)
from app.models.cliente import Cliente
from app.models.codigo_servico import CodigoServico


CNPJ_SANDRO = "33444555000199"  # demonstração
NOME_CLIENTE_SANDRO = "Operação Sandro Anestesistas"

# Códigos placeholder até a planilha real chegar — valores plausíveis
# para o segmento de anestesiologia.
CODIGOS_SEED: list[dict[str, object]] = [
    {
        "codigo": "ANE001",
        "descricao": "Anestesia geral - cirurgia de pequeno porte",
        "valor_centavos": 45000,
        "categoria": "Anestesia geral",
        "porte": "P",
    },
    {
        "codigo": "ANE002",
        "descricao": "Anestesia geral - cirurgia de médio porte",
        "valor_centavos": 75000,
        "categoria": "Anestesia geral",
        "porte": "M",
    },
    {
        "codigo": "ANE003",
        "descricao": "Anestesia geral - cirurgia de grande porte",
        "valor_centavos": 120000,
        "categoria": "Anestesia geral",
        "porte": "G",
    },
    {
        "codigo": "ANE004",
        "descricao": "Anestesia raquidiana",
        "valor_centavos": 55000,
        "categoria": "Anestesia regional",
        "porte": "M",
    },
    {
        "codigo": "ANE005",
        "descricao": "Anestesia peridural",
        "valor_centavos": 60000,
        "categoria": "Anestesia regional",
        "porte": "M",
    },
    {
        "codigo": "ANE006",
        "descricao": "Bloqueio de plexo braquial",
        "valor_centavos": 48000,
        "categoria": "Bloqueio regional",
        "porte": "M",
    },
    {
        "codigo": "ANE007",
        "descricao": "Sedação para procedimento endoscópico",
        "valor_centavos": 30000,
        "categoria": "Sedação",
        "porte": "P",
    },
    {
        "codigo": "ANE008",
        "descricao": "Anestesia obstétrica - cesárea",
        "valor_centavos": 70000,
        "categoria": "Obstétrica",
        "porte": "M",
    },
    {
        "codigo": "ANE009",
        "descricao": "Anestesia pediátrica - cirurgia de médio porte",
        "valor_centavos": 90000,
        "categoria": "Pediátrica",
        "porte": "M",
    },
    {
        "codigo": "ANE010",
        "descricao": "Anestesia cardiovascular - cirurgia complexa",
        "valor_centavos": 180000,
        "categoria": "Cardiovascular",
        "porte": "GG",
    },
]


# 5 médicos fictícios. CRMs no formato normalizado (dígitos/UF).
MEDICOS_SEED: list[dict[str, str]] = [
    {
        "nome": "DR. RICARDO ANDRADE",
        "crm": "12345/SP",
        "cpf": "11122233396",
        "especialidade": "Anestesiologia",
    },
    {
        "nome": "DRA. PATRICIA LIMA",
        "crm": "23456/SP",
        "cpf": "22233344407",
        "especialidade": "Anestesiologia",
    },
    {
        "nome": "DR. FERNANDO COSTA",
        "crm": "34567/SP",
        "cpf": "33344455518",
        "especialidade": "Anestesiologia",
    },
    {
        "nome": "DRA. CAROLINA MENDES",
        "crm": "45678/SP",
        "cpf": "44455566629",
        "especialidade": "Anestesiologia Pediátrica",
    },
    {
        "nome": "DR. EDUARDO SANTOS",
        "crm": "56789/SP",
        "cpf": "55566677730",
        "especialidade": "Anestesiologia Cardiovascular",
    },
]


async def _get_or_create_cliente() -> UUID:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Cliente).where(Cliente.cnpj == CNPJ_SANDRO)
        )
        cli = result.scalar_one_or_none()
        if cli is not None:
            print(f"[=] Cliente já existe: {cli.nome} ({cli.id})")
            return cli.id

        cli = Cliente(
            nome=NOME_CLIENTE_SANDRO,
            cnpj=CNPJ_SANDRO,
            email_contato="sandro@operacao.demo",
            telefone="(11) 99999-9999",
            observacoes=(
                "Cliente do caso Sandro — opera ~60 anestesistas, fluxo de "
                "autoatendimento por CRM. Dados de seed enquanto a planilha "
                "real não chega."
            ),
            ativo=True,
        )
        db.add(cli)
        await db.flush()
        await db.commit()
        print(f"[+] Cliente criado: {cli.nome} ({cli.id})")
        return cli.id


async def _seed_codigos(cliente_id: UUID) -> None:
    criados = 0
    inalterados = 0
    async with AsyncSessionLocal() as db:
        for c in CODIGOS_SEED:
            existing = await db.execute(
                select(CodigoServico)
                .where(CodigoServico.cliente_id == cliente_id)
                .where(CodigoServico.codigo == c["codigo"])
            )
            if existing.scalar_one_or_none() is not None:
                inalterados += 1
                continue
            cod = CodigoServico(
                cliente_id=cliente_id,
                codigo=str(c["codigo"]),
                descricao=str(c["descricao"]),
                valor_centavos=int(c["valor_centavos"]),  # type: ignore[arg-type]
                categoria=str(c["categoria"]),
                porte=str(c["porte"]),
            )
            db.add(cod)
            criados += 1
        await db.commit()
    print(f"[+] Códigos: {criados} criados, {inalterados} já existiam.")


async def _seed_medicos(cliente_id: UUID) -> None:
    criados = 0
    inalterados = 0
    async with AsyncSessionLocal() as db:
        for m in MEDICOS_SEED:
            cpf = m["cpf"]
            cpf_hash = hash_for_lookup(cpf)
            existing = await db.execute(
                select(Beneficiario)
                .where(Beneficiario.cliente_id == cliente_id)
                .where(Beneficiario.cpf_hash == cpf_hash)
            )
            if existing.scalar_one_or_none() is not None:
                inalterados += 1
                continue

            ben = Beneficiario(
                cliente_id=cliente_id,
                cpf_encrypted=encrypt(cpf),
                cpf_hash=cpf_hash,
                cpf_mascarado=mask_cpf(cpf),
                nome=m["nome"],
                crm=m["crm"],
                categoria="Médico",
                especialidade=m["especialidade"],
                status=StatusBeneficiario.ATIVO,
                origem_cadastro=OrigemCadastroBeneficiario.SEED,
                ativo=True,
            )
            db.add(ben)
            criados += 1
        await db.commit()
    print(f"[+] Médicos: {criados} criados, {inalterados} já existiam.")


async def main() -> None:
    print("=" * 60)
    print("MedPag — Seed do fluxo Anestesista (caso Sandro)")
    print("=" * 60)
    cliente_id = await _get_or_create_cliente()
    await _seed_codigos(cliente_id)
    await _seed_medicos(cliente_id)
    print("-" * 60)
    print("CRMs de teste:")
    for m in MEDICOS_SEED:
        print(f"   {m['crm']:<12} — {m['nome']}")
    print("=" * 60)
    print("[OK] Seed do fluxo anestesista concluído.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
