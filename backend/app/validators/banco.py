"""Validador de dados bancários (banco, agência, conta).

Mantém tabela básica de bancos FEBRABAN com regras específicas de
validação de agência e conta por banco. Foco inicial: Unicred.

Para expandir suporte a um novo banco, basta adicionar entrada em
`_BANCOS_SUPORTADOS` com as regras dele.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StatusBanco(str, Enum):
    """Status da validação bancária."""

    VALIDO = "VALIDO"
    INVALIDO = "INVALIDO"
    NAO_SUPORTADO = "NAO_SUPORTADO"  # Banco existe mas não está implementado


@dataclass(frozen=True, slots=True)
class RegraBanco:
    """Define as regras de validação de um banco."""

    codigo: str  # Código FEBRABAN (3 dígitos)
    nome: str
    agencia_tamanho_min: int
    agencia_tamanho_max: int
    conta_tamanho_min: int
    conta_tamanho_max: int
    suportado: bool = True


@dataclass(frozen=True, slots=True)
class ResultadoValidacaoBanco:
    """Resultado da validação de dados bancários."""

    status: StatusBanco
    banco_codigo: str | None
    banco_nome: str | None
    agencia_limpa: str | None
    conta_limpa: str | None
    codigo_erro: str | None
    mensagem: str

    @property
    def is_valido(self) -> bool:
        return self.status == StatusBanco.VALIDO


# ============================================================
# Tabela FEBRABAN
# ============================================================
# Inclui os bancos mais usados no Brasil + foco em Unicred (banco do MVP).
# Códigos extraídos de https://www.bcb.gov.br/

_BANCOS_SUPORTADOS: dict[str, RegraBanco] = {
    "136": RegraBanco(
        codigo="136",
        nome="Unicred",
        agencia_tamanho_min=4,
        agencia_tamanho_max=4,
        conta_tamanho_min=5,
        conta_tamanho_max=10,
        suportado=True,
    ),
    "001": RegraBanco(
        codigo="001",
        nome="Banco do Brasil",
        agencia_tamanho_min=4,
        agencia_tamanho_max=4,
        conta_tamanho_min=5,
        conta_tamanho_max=9,
        suportado=False,  # Será suportado na Fase 2
    ),
    "033": RegraBanco(
        codigo="033",
        nome="Santander",
        agencia_tamanho_min=4,
        agencia_tamanho_max=4,
        conta_tamanho_min=8,
        conta_tamanho_max=9,
        suportado=False,
    ),
    "104": RegraBanco(
        codigo="104",
        nome="Caixa Econômica",
        agencia_tamanho_min=4,
        agencia_tamanho_max=4,
        conta_tamanho_min=6,
        conta_tamanho_max=11,
        suportado=False,
    ),
    "237": RegraBanco(
        codigo="237",
        nome="Bradesco",
        agencia_tamanho_min=4,
        agencia_tamanho_max=4,
        conta_tamanho_min=7,
        conta_tamanho_max=7,
        suportado=False,
    ),
    "341": RegraBanco(
        codigo="341",
        nome="Itaú",
        agencia_tamanho_min=4,
        agencia_tamanho_max=4,
        conta_tamanho_min=5,
        conta_tamanho_max=6,
        suportado=False,
    ),
    "748": RegraBanco(
        codigo="748",
        nome="Sicredi",
        agencia_tamanho_min=4,
        agencia_tamanho_max=4,
        conta_tamanho_min=5,
        conta_tamanho_max=10,
        suportado=False,
    ),
    "756": RegraBanco(
        codigo="756",
        nome="Sicoob",
        agencia_tamanho_min=4,
        agencia_tamanho_max=4,
        conta_tamanho_min=5,
        conta_tamanho_max=10,
        suportado=False,
    ),
    "260": RegraBanco(
        codigo="260",
        nome="Nubank",
        agencia_tamanho_min=4,
        agencia_tamanho_max=4,
        conta_tamanho_min=6,
        conta_tamanho_max=11,
        suportado=False,
    ),
    "077": RegraBanco(
        codigo="077",
        nome="Banco Inter",
        agencia_tamanho_min=4,
        agencia_tamanho_max=4,
        conta_tamanho_min=6,
        conta_tamanho_max=10,
        suportado=False,
    ),
}


# ============================================================
# Funções auxiliares
# ============================================================


def normalizar_codigo_banco(codigo_raw: str | int | None) -> str:
    """Normaliza código de banco para 3 dígitos com zero à esquerda."""
    if codigo_raw is None or codigo_raw == "":
        return ""
    codigo = "".join(c for c in str(codigo_raw) if c.isdigit())
    return codigo.zfill(3) if codigo else ""


def limpar_agencia(agencia_raw: str | None) -> str:
    """Remove tudo que não é dígito da agência."""
    if not agencia_raw:
        return ""
    return "".join(c for c in str(agencia_raw) if c.isdigit())


def limpar_conta(conta_raw: str | None) -> str:
    """Remove tudo que não é dígito ou X (DV) da conta."""
    if not conta_raw:
        return ""
    return "".join(c for c in str(conta_raw).upper() if c.isdigit() or c == "X")


def obter_banco(codigo: str) -> RegraBanco | None:
    """Retorna a regra do banco se conhecido, None caso contrário."""
    codigo_normalizado = normalizar_codigo_banco(codigo)
    return _BANCOS_SUPORTADOS.get(codigo_normalizado)


def listar_bancos_suportados() -> list[RegraBanco]:
    """Lista bancos com suporte completo (gerar CNAB)."""
    return [b for b in _BANCOS_SUPORTADOS.values() if b.suportado]


# ============================================================
# Função principal
# ============================================================


def validar_dados_bancarios(
    banco_raw: str | int | None,
    agencia_raw: str | None,
    conta_raw: str | None,
) -> ResultadoValidacaoBanco:
    """Valida combinação banco + agência + conta.

    Args:
        banco_raw: Código do banco (3 dígitos, pode vir com zero faltando)
        agencia_raw: Número da agência
        conta_raw: Número da conta (pode ter dígito verificador)

    Returns:
        ResultadoValidacaoBanco com status e mensagens
    """
    # Normaliza inputs
    banco_codigo = normalizar_codigo_banco(banco_raw)
    agencia_limpa = limpar_agencia(agencia_raw)
    conta_limpa = limpar_conta(conta_raw)

    # Validação 1: banco informado?
    if not banco_codigo:
        return ResultadoValidacaoBanco(
            status=StatusBanco.INVALIDO,
            banco_codigo=None,
            banco_nome=None,
            agencia_limpa=agencia_limpa or None,
            conta_limpa=conta_limpa or None,
            codigo_erro="BANCO_INVALIDO",
            mensagem="Código do banco não informado",
        )

    # Validação 2: banco conhecido?
    regra = obter_banco(banco_codigo)
    if regra is None:
        return ResultadoValidacaoBanco(
            status=StatusBanco.INVALIDO,
            banco_codigo=banco_codigo,
            banco_nome=None,
            agencia_limpa=agencia_limpa or None,
            conta_limpa=conta_limpa or None,
            codigo_erro="BANCO_INVALIDO",
            mensagem=f"Código de banco '{banco_codigo}' não consta na tabela FEBRABAN",
        )

    # Validação 3: banco suportado pelo sistema?
    if not regra.suportado:
        return ResultadoValidacaoBanco(
            status=StatusBanco.NAO_SUPORTADO,
            banco_codigo=banco_codigo,
            banco_nome=regra.nome,
            agencia_limpa=agencia_limpa or None,
            conta_limpa=conta_limpa or None,
            codigo_erro="BANCO_NAO_SUPORTADO",
            mensagem=(
                f"{regra.nome} ainda não está habilitado no sistema. "
                f"Suporte previsto para próximas versões."
            ),
        )

    # Validação 4: agência
    if not agencia_limpa:
        return ResultadoValidacaoBanco(
            status=StatusBanco.INVALIDO,
            banco_codigo=banco_codigo,
            banco_nome=regra.nome,
            agencia_limpa=None,
            conta_limpa=conta_limpa or None,
            codigo_erro="AGENCIA_INVALIDA",
            mensagem="Agência não informada",
        )

    if not (regra.agencia_tamanho_min <= len(agencia_limpa) <= regra.agencia_tamanho_max):
        return ResultadoValidacaoBanco(
            status=StatusBanco.INVALIDO,
            banco_codigo=banco_codigo,
            banco_nome=regra.nome,
            agencia_limpa=agencia_limpa,
            conta_limpa=conta_limpa or None,
            codigo_erro="AGENCIA_INVALIDA",
            mensagem=(
                f"Agência {regra.nome} deve ter entre {regra.agencia_tamanho_min} "
                f"e {regra.agencia_tamanho_max} dígitos (recebido: {len(agencia_limpa)})"
            ),
        )

    # Validação 5: conta
    if not conta_limpa:
        return ResultadoValidacaoBanco(
            status=StatusBanco.INVALIDO,
            banco_codigo=banco_codigo,
            banco_nome=regra.nome,
            agencia_limpa=agencia_limpa,
            conta_limpa=None,
            codigo_erro="CONTA_INVALIDA",
            mensagem="Conta não informada",
        )

    if not (regra.conta_tamanho_min <= len(conta_limpa) <= regra.conta_tamanho_max):
        return ResultadoValidacaoBanco(
            status=StatusBanco.INVALIDO,
            banco_codigo=banco_codigo,
            banco_nome=regra.nome,
            agencia_limpa=agencia_limpa,
            conta_limpa=conta_limpa,
            codigo_erro="CONTA_INVALIDA",
            mensagem=(
                f"Conta {regra.nome} deve ter entre {regra.conta_tamanho_min} "
                f"e {regra.conta_tamanho_max} dígitos (recebido: {len(conta_limpa)})"
            ),
        )

    # Tudo OK
    return ResultadoValidacaoBanco(
        status=StatusBanco.VALIDO,
        banco_codigo=banco_codigo,
        banco_nome=regra.nome,
        agencia_limpa=agencia_limpa,
        conta_limpa=conta_limpa,
        codigo_erro=None,
        mensagem=f"Dados bancários válidos ({regra.nome})",
    )
