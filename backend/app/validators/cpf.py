"""Validador de CPF com correção inteligente.

Identifica os erros mais comuns em planilhas:
- Zero à esquerda perdido pelo Excel (CPF com 10 dígitos)
- Formatação inconsistente (com/sem pontos e traços)
- Caracteres invisíveis e espaços
- Sequências inválidas (111.111.111-11, etc)

REGRA CRÍTICA: Quando possível, SUGERE uma correção. NUNCA aplica
automaticamente. O aprovador (Thiago) é quem decide se aceita a sugestão.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from validate_docbr import CPF

# ============================================================
# Constantes
# ============================================================

# Sequências que passam no algoritmo módulo 11 mas são fake
_FAKE_CPFS: frozenset[str] = frozenset({
    "00000000000",
    "11111111111",
    "22222222222",
    "33333333333",
    "44444444444",
    "55555555555",
    "66666666666",
    "77777777777",
    "88888888888",
    "99999999999",
    "12345678909",  # CPF clássico de teste
})

_validator = CPF()


# ============================================================
# Tipos
# ============================================================


class CPFStatus(str, Enum):
    """Status possíveis após validação."""

    VALIDO = "VALIDO"
    INVALIDO = "INVALIDO"
    CORRIGIVEL = "CORRIGIVEL"  # Sistema tem sugestão
    VAZIO = "VAZIO"


@dataclass(frozen=True, slots=True)
class ResultadoValidacaoCPF:
    """Resultado da validação de um CPF."""

    status: CPFStatus
    cpf_original: str  # Como veio na planilha
    cpf_limpo: str | None  # Apenas dígitos
    cpf_sugerido: str | None  # Sugestão de correção
    codigo_erro: str | None  # Código padronizado (ver .cursorrules)
    mensagem: str  # Mensagem em português

    @property
    def is_valido(self) -> bool:
        return self.status == CPFStatus.VALIDO

    @property
    def is_corrigivel(self) -> bool:
        return self.status == CPFStatus.CORRIGIVEL

    @property
    def precisa_revisao(self) -> bool:
        return self.status in (CPFStatus.INVALIDO, CPFStatus.CORRIGIVEL)

    @property
    def deve_bloquear(self) -> bool:
        """True se o sistema deve bloquear este pagamento até revisão."""
        return self.status == CPFStatus.INVALIDO


# ============================================================
# Funções auxiliares
# ============================================================


def limpar_cpf(cpf_raw: str | None) -> str:
    """Remove tudo que não é dígito.

    Args:
        cpf_raw: CPF cru da planilha (pode ter pontos, traços, espaços, None)

    Returns:
        String contendo apenas dígitos
    """
    if not cpf_raw:
        return ""
    return "".join(c for c in str(cpf_raw) if c.isdigit())


def formatar_cpf(cpf_limpo: str) -> str:
    """Formata CPF como XXX.XXX.XXX-XX.

    Args:
        cpf_limpo: 11 dígitos numéricos

    Returns:
        CPF formatado, ou o próprio input se não tiver 11 dígitos
    """
    if len(cpf_limpo) != 11:
        return cpf_limpo
    return f"{cpf_limpo[:3]}.{cpf_limpo[3:6]}.{cpf_limpo[6:9]}-{cpf_limpo[9:]}"


# ============================================================
# Lógica de correção
# ============================================================


def _tentar_corrigir(cpf_limpo: str) -> str | None:
    """Tenta corrigir erros comuns. Retorna None se não conseguir.

    Estratégias:
    1. 10 dígitos → tenta prefixar zero (Excel come zero à esquerda)
    2. 12+ dígitos → tenta usar os 11 primeiros ou últimos
    3. 9 dígitos → tenta prefixar dois zeros (improvável mas possível)
    """
    candidatos: list[str] = []

    if len(cpf_limpo) == 10:
        candidatos.append("0" + cpf_limpo)

    elif len(cpf_limpo) == 9:
        candidatos.append("00" + cpf_limpo)

    elif len(cpf_limpo) > 11:
        candidatos.append(cpf_limpo[-11:])
        candidatos.append(cpf_limpo[:11])

    for candidato in candidatos:
        if (
            len(candidato) == 11
            and candidato not in _FAKE_CPFS
            and _validator.validate(candidato)
        ):
            return candidato

    return None


# ============================================================
# Função principal
# ============================================================


def validar_cpf(cpf_raw: str | None) -> ResultadoValidacaoCPF:
    """Valida um CPF e sugere correção quando possível.

    Args:
        cpf_raw: CPF como veio da planilha (pode estar formatado, sujo, vazio)

    Returns:
        ResultadoValidacaoCPF com status, código de erro e sugestão
    """
    # Caso 1: vazio
    if not cpf_raw or not str(cpf_raw).strip():
        return ResultadoValidacaoCPF(
            status=CPFStatus.VAZIO,
            cpf_original=str(cpf_raw or ""),
            cpf_limpo=None,
            cpf_sugerido=None,
            codigo_erro="CPF_VAZIO",
            mensagem="CPF não informado",
        )

    cpf_original_str = str(cpf_raw)
    cpf_limpo = limpar_cpf(cpf_raw)

    # Caso 2: sequência fake (111.111.111-11 etc)
    if cpf_limpo in _FAKE_CPFS:
        return ResultadoValidacaoCPF(
            status=CPFStatus.INVALIDO,
            cpf_original=cpf_original_str,
            cpf_limpo=cpf_limpo,
            cpf_sugerido=None,
            codigo_erro="CPF_SEQUENCIA_INVALIDA",
            mensagem="CPF inválido (sequência reconhecida como inválida)",
        )

    # Caso 3: válido como está
    if len(cpf_limpo) == 11 and _validator.validate(cpf_limpo):
        return ResultadoValidacaoCPF(
            status=CPFStatus.VALIDO,
            cpf_original=cpf_original_str,
            cpf_limpo=cpf_limpo,
            cpf_sugerido=None,
            codigo_erro=None,
            mensagem="CPF válido",
        )

    # Caso 4: corrigível
    sugestao = _tentar_corrigir(cpf_limpo)
    if sugestao:
        return ResultadoValidacaoCPF(
            status=CPFStatus.CORRIGIVEL,
            cpf_original=cpf_original_str,
            cpf_limpo=cpf_limpo,
            cpf_sugerido=sugestao,
            codigo_erro="CPF_CORRIGIVEL",
            mensagem=(
                f"CPF parece ter erro de digitação. "
                f"Sugestão: {formatar_cpf(sugestao)}"
            ),
        )

    # Caso 5: tamanho errado e sem sugestão
    if len(cpf_limpo) != 11:
        return ResultadoValidacaoCPF(
            status=CPFStatus.INVALIDO,
            cpf_original=cpf_original_str,
            cpf_limpo=cpf_limpo,
            cpf_sugerido=None,
            codigo_erro="CPF_INVALIDO",
            mensagem=f"CPF deve ter 11 dígitos, mas tem {len(cpf_limpo)}",
        )

    # Caso 6: tamanho certo mas dígito verificador errado
    return ResultadoValidacaoCPF(
        status=CPFStatus.INVALIDO,
        cpf_original=cpf_original_str,
        cpf_limpo=cpf_limpo,
        cpf_sugerido=None,
        codigo_erro="CPF_DIGITO_INVALIDO",
        mensagem="CPF com dígito verificador inválido",
    )
