"""Validação de titularidade PIX ↔ CPF/CNPJ (antifraude da cadeia de confiança).

Ideia (do mapa mental): antes de pagar/repassar, confirmar que a chave
PIX pertence ao médico cadastrado. Fecha o elo "a conta é dele" da cadeia
Vital → CRM → CPF → PIX → banco.

PF vs PJ (decisão registrada): o médico pode receber pela própria pessoa
física (CPF) OU por uma PJ (clínica, CNPJ). Por isso a verificação aceita:
    - titular CPF == CPF do médico, OU
    - titular CNPJ ∈ lista de CNPJs vinculados ao médico.

A consulta usa o Asaas (`asaas_client.consultar_chave_pix`). Enquanto o
Asaas não está liberado, `validar_titularidade_pix` devolve um veredito
PENDENTE em vez de explodir — o fluxo segue e o operador revisa manual.

A função de comparação (`comparar_titularidade`) é PURA e testável.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.services.asaas_client import (
    AsaasFalhouError,
    AsaasIndisponivelError,
    asaas_client,
)


class ResultadoPix(str, Enum):
    """Veredito da validação de titularidade."""

    CONFERE = "CONFERE"          # titular bate com o CPF/CNPJ esperado
    DIVERGENTE = "DIVERGENTE"    # titular é outra pessoa — risco de fraude
    PENDENTE = "PENDENTE"        # não deu pra verificar (Asaas off, etc.)


@dataclass(slots=True)
class VeredictoPix:
    resultado: ResultadoPix
    mensagem: str
    nome_titular: str | None = None
    doc_titular: str | None = None  # CPF/CNPJ do titular (só dígitos)


def _so_digitos(valor: str | None) -> str:
    return "".join(c for c in (valor or "") if c.isdigit())


def comparar_titularidade(
    *,
    cpf_esperado: str,
    doc_titular: str | None,
    nome_titular: str | None = None,
    cnpjs_vinculados: list[str] | None = None,
) -> VeredictoPix:
    """Compara o documento do titular da chave com o CPF esperado (PF/PJ).

    PURA — sem rede. Casa CPF direto OU CNPJ vinculado ao médico.
    """
    cpf = _so_digitos(cpf_esperado)
    titular = _so_digitos(doc_titular)
    vinculados = {_so_digitos(c) for c in (cnpjs_vinculados or []) if c}

    if not titular:
        return VeredictoPix(
            resultado=ResultadoPix.PENDENTE,
            mensagem="Titularidade não retornada pela consulta.",
            nome_titular=nome_titular,
            doc_titular=None,
        )

    if len(titular) == 11:  # titular é PF
        if titular == cpf:
            return VeredictoPix(
                resultado=ResultadoPix.CONFERE,
                mensagem="Chave PIX pertence ao CPF do médico.",
                nome_titular=nome_titular,
                doc_titular=titular,
            )
        return VeredictoPix(
            resultado=ResultadoPix.DIVERGENTE,
            mensagem="Chave PIX pertence a outro CPF.",
            nome_titular=nome_titular,
            doc_titular=titular,
        )

    if len(titular) == 14:  # titular é PJ (clínica)
        if titular in vinculados:
            return VeredictoPix(
                resultado=ResultadoPix.CONFERE,
                mensagem="Chave PIX pertence a CNPJ vinculado ao médico.",
                nome_titular=nome_titular,
                doc_titular=titular,
            )
        return VeredictoPix(
            resultado=ResultadoPix.DIVERGENTE,
            mensagem=(
                "Chave PIX pertence a um CNPJ não vinculado ao médico. "
                "Vincule a clínica ao cadastro pra liberar."
            ),
            nome_titular=nome_titular,
            doc_titular=titular,
        )

    return VeredictoPix(
        resultado=ResultadoPix.PENDENTE,
        mensagem=f"Documento do titular em formato inesperado: {titular}",
        nome_titular=nome_titular,
        doc_titular=titular,
    )


async def validar_titularidade_pix(
    *,
    chave_pix: str,
    cpf_esperado: str,
    cnpjs_vinculados: list[str] | None = None,
) -> VeredictoPix:
    """Consulta o Asaas e compara a titularidade da chave com o CPF do médico.

    Falha graciosa: se o Asaas não estiver configurado/disponível, devolve
    PENDENTE (não bloqueia a operação — sinaliza pra revisão manual).
    """
    if not asaas_client.is_configured():
        return VeredictoPix(
            resultado=ResultadoPix.PENDENTE,
            mensagem="Asaas não configurado — verificação manual necessária.",
        )

    try:
        data = await asaas_client.consultar_chave_pix(chave_pix)
    except (AsaasIndisponivelError, AsaasFalhouError) as exc:
        return VeredictoPix(
            resultado=ResultadoPix.PENDENTE,
            mensagem=f"Não foi possível consultar a chave agora: {exc}",
        )

    # Tenta extrair nome/documento de formatos comuns do payload Asaas.
    titular = _extrair_titular(data)
    return comparar_titularidade(
        cpf_esperado=cpf_esperado,
        doc_titular=titular.get("doc"),
        nome_titular=titular.get("nome"),
        cnpjs_vinculados=cnpjs_vinculados,
    )


def _extrair_titular(data: dict) -> dict[str, str | None]:
    """Best-effort: garimpa nome + CPF/CNPJ do titular no payload do Asaas.

    O shape exato depende do endpoint liberado; olhamos as chaves mais
    prováveis (receiver/owner/pixKey...) sem quebrar se faltar.
    """
    candidatos_doc = ("cpfCnpj", "ownerCpfCnpj", "receiverCpfCnpj", "documentNumber")
    candidatos_nome = ("name", "ownerName", "receiverName", "holderName")

    # achata 1 nível: olha o dict raiz e sub-dicts comuns
    blocos: list[dict] = [data]
    for chave in ("receiver", "owner", "pixKey", "account"):
        sub = data.get(chave)
        if isinstance(sub, dict):
            blocos.append(sub)

    doc: str | None = None
    nome: str | None = None
    for bloco in blocos:
        if doc is None:
            for k in candidatos_doc:
                if bloco.get(k):
                    doc = str(bloco[k])
                    break
        if nome is None:
            for k in candidatos_nome:
                if bloco.get(k):
                    nome = str(bloco[k])
                    break
    return {"doc": doc, "nome": nome}


__all__ = [
    "ResultadoPix",
    "VeredictoPix",
    "comparar_titularidade",
    "validar_titularidade_pix",
]
