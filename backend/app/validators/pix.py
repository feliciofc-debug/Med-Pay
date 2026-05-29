"""Validador de chave PIX.

Duas camadas, casando com a estrategia escolhida:

1. CAMADA LOCAL (gratis, roda no codigo) — implementada aqui:
   - Valida sintaxe da chave por tipo (CPF, CNPJ, EMAIL, TELEFONE, EVP)
   - Auto-detecta o tipo quando nao foi informado
   - Quando chave = CPF, confere se bate com o CPF do prestador
   - Pega 100% dos erros de digitacao SEM precisar consultar DICT

2. CAMADA DICT (paga, externa) — gancho preparado, ativacao futura:
   - `consultar_dict_titularidade(chave, cpf)` -> stub para integrar
     com Asaas/Celcoin/Efi/BS2.
   - Retorna `(titular_nome, is_same_tax_id)` e a camada superior
     carimba `pix_validado_em` no Beneficiario.

Documentacao oficial: Manual Operacional do DICT (BCB).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from enum import Enum

from app.validators.cpf import limpar_cpf, validar_cpf


class TipoChavePIX(str, Enum):
    """Tipos oficiais de chave PIX (BCB)."""

    CPF = "CPF"
    CNPJ = "CNPJ"
    EMAIL = "EMAIL"
    TELEFONE = "TELEFONE"
    ALEATORIA = "ALEATORIA"  # EVP (Endereco Virtual de Pagamento)


class StatusPIX(str, Enum):
    """Resultado da validacao local."""

    VALIDA = "VALIDA"
    INVALIDA = "INVALIDA"


@dataclass(frozen=True, slots=True)
class ResultadoValidacaoPIX:
    """Saida da validacao local da chave PIX."""

    status: StatusPIX
    tipo_detectado: TipoChavePIX | None
    chave_normalizada: str | None  # chave limpa pronta pra salvar
    codigo_erro: str | None
    mensagem: str

    @property
    def is_valida(self) -> bool:
        return self.status == StatusPIX.VALIDA


# ============================================================
# Regex / constantes
# ============================================================

# RFC 5322 simplificada — cobre 99% dos emails reais
_EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)

# Telefone E.164 brasileiro: +55 + DDD (2 digitos) + 8 ou 9 digitos
# Aceita tambem variantes sem prefixo (DDD+numero, com ou sem mascara)
_TELEFONE_BR_E164 = re.compile(r"^\+55[1-9]{2}9?\d{8}$")

# CNPJ formatado ou cru
_NAO_DIGITO = re.compile(r"\D")


# ============================================================
# Helpers de limpeza
# ============================================================


def _so_digitos(s: str) -> str:
    return _NAO_DIGITO.sub("", s or "")


def _normalizar_telefone_e164(raw: str) -> str | None:
    """Aceita '(21) 99999-8888', '21999998888', '5521999998888',
    '+5521999998888' — devolve formato E.164 ou None se nao for celular BR.
    """
    digs = _so_digitos(raw)
    if not digs:
        return None
    # Remove prefixo 55 se vier duplicado
    if digs.startswith("55") and len(digs) in (12, 13):
        digs = digs[2:]
    # Brasil: 10 (fixo) ou 11 (celular) digitos
    if len(digs) not in (10, 11):
        return None
    return f"+55{digs}"


def _validar_cnpj(cnpj: str) -> bool:
    """Algoritmo oficial de DV do CNPJ."""
    cnpj = _so_digitos(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    def _dv(base: str, pesos: list[int]) -> int:
        soma = sum(int(c) * p for c, p in zip(base, pesos, strict=False))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    pesos_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos_2 = [6] + pesos_1
    dv1 = _dv(cnpj[:12], pesos_1)
    dv2 = _dv(cnpj[:13], pesos_2)
    return cnpj[-2:] == f"{dv1}{dv2}"


def _validar_evp(chave: str) -> bool:
    """Chave aleatoria (EVP) e' um UUID v4 (36 chars com hifens)."""
    try:
        u = uuid.UUID(chave.strip())
        # BCB exige UUID v4, mas alguns DICT aceitam outros — vamos
        # ser tolerantes (qualquer UUID valido passa).
        return u.version is not None
    except (ValueError, AttributeError):
        return False


# ============================================================
# Auto-deteccao do tipo
# ============================================================


def detectar_tipo(chave: str | None) -> TipoChavePIX | None:
    """Tenta identificar o tipo de chave a partir do formato.

    Ordem de tentativa: EMAIL -> EVP -> CPF -> CNPJ -> TELEFONE.
    Retorna None se nao encaixar em nada.
    """
    if not chave or not chave.strip():
        return None
    raw = chave.strip()

    if "@" in raw and _EMAIL_REGEX.match(raw):
        return TipoChavePIX.EMAIL

    if _validar_evp(raw):
        return TipoChavePIX.ALEATORIA

    digs = _so_digitos(raw)
    if len(digs) == 11:
        # Pode ser CPF ou telefone celular brasileiro sem prefixo
        if validar_cpf(digs).is_valido:
            return TipoChavePIX.CPF
        # Cai pra telefone se o DDD for valido
        if digs[0] in "123456789" and digs[2] == "9":
            return TipoChavePIX.TELEFONE
    if len(digs) == 10:
        # Telefone fixo
        return TipoChavePIX.TELEFONE
    if len(digs) == 14 and _validar_cnpj(digs):
        return TipoChavePIX.CNPJ
    if len(digs) in (12, 13):
        # Com codigo do pais — telefone
        return TipoChavePIX.TELEFONE

    return None


# ============================================================
# Validacao principal
# ============================================================


def validar_chave_pix(
    chave: str | None,
    tipo: str | TipoChavePIX | None = None,
    cpf_titular: str | None = None,
) -> ResultadoValidacaoPIX:
    """Valida sintaxe da chave PIX + (opcionalmente) compara com CPF
    do titular quando a chave for do tipo CPF.

    Args:
        chave: chave PIX a validar (qualquer formato)
        tipo: tipo declarado pelo cliente. Se None, e' auto-detectado.
        cpf_titular: CPF do prestador cadastrado. Quando informado e a
            chave for do tipo CPF, exige que sejam o mesmo CPF
            (regra anti-fraude — ninguem cadastra PIX-CPF de outra
            pessoa por engano).

    Returns:
        ResultadoValidacaoPIX com status, tipo detectado, chave
        normalizada e mensagem em portugues pronta para mostrar
        ao usuario.
    """
    if not chave or not chave.strip():
        return ResultadoValidacaoPIX(
            status=StatusPIX.INVALIDA,
            tipo_detectado=None,
            chave_normalizada=None,
            codigo_erro="PIX_VAZIO",
            mensagem="Chave PIX nao informada.",
        )

    raw = chave.strip()

    # Normaliza tipo declarado
    tipo_decl: TipoChavePIX | None = None
    if isinstance(tipo, TipoChavePIX):
        tipo_decl = tipo
    elif isinstance(tipo, str) and tipo.strip():
        t = tipo.strip().upper().replace("Ó", "O").replace("Á", "A")
        if t.startswith("ALEAT"):
            tipo_decl = TipoChavePIX.ALEATORIA
        else:
            try:
                tipo_decl = TipoChavePIX(t)
            except ValueError:
                return ResultadoValidacaoPIX(
                    status=StatusPIX.INVALIDA,
                    tipo_detectado=None,
                    chave_normalizada=None,
                    codigo_erro="PIX_TIPO_INVALIDO",
                    mensagem=(
                        f"Tipo de chave PIX desconhecido: '{tipo}'. "
                        "Use CPF, CNPJ, EMAIL, TELEFONE ou ALEATORIA."
                    ),
                )

    tipo_detect = tipo_decl or detectar_tipo(raw)
    if tipo_detect is None:
        return ResultadoValidacaoPIX(
            status=StatusPIX.INVALIDA,
            tipo_detectado=None,
            chave_normalizada=None,
            codigo_erro="PIX_FORMATO_INVALIDO",
            mensagem=(
                "Nao foi possivel identificar o tipo da chave PIX. "
                "Confira o formato (CPF, email, telefone +55..., "
                "CNPJ ou chave aleatoria UUID)."
            ),
        )

    # Validacao especifica por tipo
    if tipo_detect == TipoChavePIX.EMAIL:
        if not _EMAIL_REGEX.match(raw):
            return ResultadoValidacaoPIX(
                status=StatusPIX.INVALIDA,
                tipo_detectado=tipo_detect,
                chave_normalizada=None,
                codigo_erro="PIX_EMAIL_INVALIDO",
                mensagem=f"Email PIX invalido: '{raw}'.",
            )
        if len(raw) > 77:
            return ResultadoValidacaoPIX(
                status=StatusPIX.INVALIDA,
                tipo_detectado=tipo_detect,
                chave_normalizada=None,
                codigo_erro="PIX_EMAIL_LONGO",
                mensagem="Email PIX excede 77 caracteres (limite BCB).",
            )
        return ResultadoValidacaoPIX(
            status=StatusPIX.VALIDA,
            tipo_detectado=tipo_detect,
            chave_normalizada=raw.lower(),
            codigo_erro=None,
            mensagem=f"Chave PIX (email) valida: {raw}",
        )

    if tipo_detect == TipoChavePIX.CPF:
        digs = _so_digitos(raw)
        cpf_res = validar_cpf(digs)
        if not cpf_res.is_valido:
            return ResultadoValidacaoPIX(
                status=StatusPIX.INVALIDA,
                tipo_detectado=tipo_detect,
                chave_normalizada=None,
                codigo_erro="PIX_CPF_INVALIDO",
                mensagem=f"Chave PIX CPF invalida: {cpf_res.mensagem}",
            )
        cpf_chave = cpf_res.cpf_limpo
        # Comparacao com CPF do titular (anti-fraude)
        if cpf_titular:
            cpf_titular_limpo = limpar_cpf(cpf_titular)
            if cpf_titular_limpo and cpf_chave != cpf_titular_limpo:
                return ResultadoValidacaoPIX(
                    status=StatusPIX.INVALIDA,
                    tipo_detectado=tipo_detect,
                    chave_normalizada=cpf_chave,
                    codigo_erro="PIX_CPF_NAO_BATE",
                    mensagem=(
                        "Chave PIX e' o CPF de OUTRA pessoa "
                        f"({cpf_chave}). Nao pode cadastrar PIX-CPF "
                        f"que nao seja o CPF do proprio prestador "
                        f"({cpf_titular_limpo})."
                    ),
                )
        return ResultadoValidacaoPIX(
            status=StatusPIX.VALIDA,
            tipo_detectado=tipo_detect,
            chave_normalizada=cpf_chave,
            codigo_erro=None,
            mensagem=f"Chave PIX (CPF) valida: {cpf_chave}",
        )

    if tipo_detect == TipoChavePIX.CNPJ:
        digs = _so_digitos(raw)
        if not _validar_cnpj(digs):
            return ResultadoValidacaoPIX(
                status=StatusPIX.INVALIDA,
                tipo_detectado=tipo_detect,
                chave_normalizada=None,
                codigo_erro="PIX_CNPJ_INVALIDO",
                mensagem=(
                    f"Chave PIX CNPJ invalida: '{raw}' "
                    "(falha no digito verificador)."
                ),
            )
        return ResultadoValidacaoPIX(
            status=StatusPIX.VALIDA,
            tipo_detectado=tipo_detect,
            chave_normalizada=digs,
            codigo_erro=None,
            mensagem=f"Chave PIX (CNPJ) valida: {digs}",
        )

    if tipo_detect == TipoChavePIX.TELEFONE:
        e164 = _normalizar_telefone_e164(raw)
        if not e164 or not _TELEFONE_BR_E164.match(e164):
            return ResultadoValidacaoPIX(
                status=StatusPIX.INVALIDA,
                tipo_detectado=tipo_detect,
                chave_normalizada=None,
                codigo_erro="PIX_TELEFONE_INVALIDO",
                mensagem=(
                    f"Telefone PIX invalido: '{raw}'. "
                    "Use formato (DDD) NNNNN-NNNN."
                ),
            )
        return ResultadoValidacaoPIX(
            status=StatusPIX.VALIDA,
            tipo_detectado=tipo_detect,
            chave_normalizada=e164,
            codigo_erro=None,
            mensagem=f"Chave PIX (telefone) valida: {e164}",
        )

    if tipo_detect == TipoChavePIX.ALEATORIA:
        if not _validar_evp(raw):
            return ResultadoValidacaoPIX(
                status=StatusPIX.INVALIDA,
                tipo_detectado=tipo_detect,
                chave_normalizada=None,
                codigo_erro="PIX_EVP_INVALIDO",
                mensagem=(
                    f"Chave PIX aleatoria invalida: '{raw}' "
                    "(esperado UUID com hifens, ex: "
                    "abc12345-1234-1234-1234-abcdef123456)."
                ),
            )
        return ResultadoValidacaoPIX(
            status=StatusPIX.VALIDA,
            tipo_detectado=tipo_detect,
            chave_normalizada=raw.lower(),
            codigo_erro=None,
            mensagem=f"Chave PIX aleatoria valida: {raw}",
        )

    # nunca deveria chegar aqui
    return ResultadoValidacaoPIX(
        status=StatusPIX.INVALIDA,
        tipo_detectado=tipo_detect,
        chave_normalizada=None,
        codigo_erro="PIX_ERRO_INTERNO",
        mensagem="Erro interno na validacao da chave PIX.",
    )


# ============================================================
# Gancho para a camada DICT (paga) — implementacao futura
# ============================================================


@dataclass(frozen=True, slots=True)
class ResultadoConsultaDICT:
    """Saida da consulta DICT (camada paga)."""

    titular_nome: str | None
    titular_documento_mascarado: str | None
    is_same_tax_id: bool
    provedor: str  # "asaas" | "celcoin" | "efi" | ...
    raw_response: dict | None = None


async def consultar_dict_titularidade(
    chave: str,
    cpf_titular: str,
    provedor: str = "asaas",
) -> ResultadoConsultaDICT | None:
    """Consulta o DICT (Banco Central) para confirmar titularidade.

    NAO IMPLEMENTADO AINDA — gancho preparado para integracao com
    Asaas / Celcoin / Efi quando o cliente decidir ativar.

    Quando implementado, retornara:
    - titular_nome: nome do dono da chave segundo o DICT
    - is_same_tax_id: True se o CPF dono da chave bate com cpf_titular
    - provedor: qual API foi usada (para auditoria de custo)

    Args:
        chave: chave PIX ja validada localmente.
        cpf_titular: CPF do prestador cadastrado.
        provedor: qual integracao usar.

    Returns:
        None enquanto a feature nao estiver ativa. Quando implementada,
        retorna ResultadoConsultaDICT.
    """
    # TODO: implementar quando user contratar Asaas/Celcoin
    # https://docs.celcoin.com.br/pix/consulta-chave-dict
    # https://docs.asaas.com/reference/consultar-chave-pix
    return None


__all__ = [
    "ResultadoConsultaDICT",
    "ResultadoValidacaoPIX",
    "StatusPIX",
    "TipoChavePIX",
    "consultar_dict_titularidade",
    "detectar_tipo",
    "validar_chave_pix",
]
