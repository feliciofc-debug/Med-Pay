"""Validador de valores monetários.

Aceita formatos típicos vindos de planilha brasileira:
- "R$ 1.234,56" → 123456 centavos
- "1234,56" → 123456 centavos
- "1234.56" → 123456 centavos
- 1234.56 (float) → 123456 centavos
- 1234 (int) → 123400 centavos (assume reais)
- Decimal("1234.56") → 123456 centavos

REGRA: o sistema sempre armazena em centavos (int). Valores em reais
só aparecem na exibição.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum


class ValorStatus(str, Enum):
    VALIDO = "VALIDO"
    INVALIDO = "INVALIDO"
    SUSPEITO = "SUSPEITO"  # fora do range esperado


@dataclass(frozen=True, slots=True)
class ResultadoValidacaoValor:
    status: ValorStatus
    valor_centavos: int | None
    valor_original: str
    codigo_erro: str | None
    mensagem: str

    @property
    def is_valido(self) -> bool:
        return self.status == ValorStatus.VALIDO


# Pattern flexível: aceita 1.234,56 ; 1234.56 ; 1,234.56 etc
_LIMPEZA_RE = re.compile(r"[^\d,.\-]")


def parsear_valor_para_centavos(valor_raw: str | int | float | None) -> int | None:
    """Converte valor cru em inteiro de centavos.

    Returns None se não conseguir parsear.
    """
    if valor_raw is None or valor_raw == "":
        return None

    if isinstance(valor_raw, int) and not isinstance(valor_raw, bool):
        # int puro: assume que já está em REAIS (ex: 1500 = R$1500,00)
        # NUNCA confiamos que esteja em centavos diretamente porque o
        # Excel/Pandas leria "1500.00" como float, não int.
        return valor_raw * 100

    if isinstance(valor_raw, float):
        # Cuidado com float: usa Decimal pra precisão
        try:
            d = Decimal(str(valor_raw))
        except InvalidOperation:
            return None
        return int((d * 100).quantize(Decimal("1")))

    s = str(valor_raw).strip()
    if not s:
        return None

    # Remove R$, espaços, etc
    s = _LIMPEZA_RE.sub("", s)
    if not s:
        return None

    # Identifica separador decimal:
    # - Se tem ',' E '.' → '.' é milhar, ',' é decimal (formato BR)
    # - Se tem só ',' → é decimal
    # - Se tem só '.' → pode ser decimal OU milhar, mas se tiver < 3 dígitos depois é decimal
    if "," in s and "." in s:
        # Formato BR: 1.234,56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    # Se só tem '.', mantém como está (já é decimal)

    try:
        d = Decimal(s)
    except InvalidOperation:
        return None

    return int((d * 100).quantize(Decimal("1")))


def validar_valor(
    valor_raw: str | int | float | None,
    *,
    valor_min_centavos: int = 100,
    valor_max_centavos: int = 100_000_00,
) -> ResultadoValidacaoValor:
    """Valida um valor monetário.

    Args:
        valor_raw: valor como veio da planilha
        valor_min_centavos: valor mínimo aceito (default R$ 1,00)
        valor_max_centavos: valor máximo aceito (default R$ 100.000,00)

    Returns:
        Resultado com status, código de erro e valor parseado em centavos
    """
    if valor_raw is None or str(valor_raw).strip() == "":
        return ResultadoValidacaoValor(
            status=ValorStatus.INVALIDO,
            valor_centavos=None,
            valor_original="",
            codigo_erro="VALOR_FORMATO_INVALIDO",
            mensagem="Valor não informado",
        )

    centavos = parsear_valor_para_centavos(valor_raw)
    if centavos is None:
        return ResultadoValidacaoValor(
            status=ValorStatus.INVALIDO,
            valor_centavos=None,
            valor_original=str(valor_raw),
            codigo_erro="VALOR_FORMATO_INVALIDO",
            mensagem=f"Valor '{valor_raw}' não pôde ser interpretado como número",
        )

    if centavos <= 0:
        return ResultadoValidacaoValor(
            status=ValorStatus.INVALIDO,
            valor_centavos=centavos,
            valor_original=str(valor_raw),
            codigo_erro="VALOR_ZERO",
            mensagem="Valor deve ser maior que zero",
        )

    if centavos < valor_min_centavos:
        return ResultadoValidacaoValor(
            status=ValorStatus.SUSPEITO,
            valor_centavos=centavos,
            valor_original=str(valor_raw),
            codigo_erro="VALOR_SUSPEITO",
            mensagem=(
                f"Valor abaixo do mínimo esperado "
                f"(R$ {valor_min_centavos / 100:.2f}). Confirme."
            ),
        )

    if centavos > valor_max_centavos:
        return ResultadoValidacaoValor(
            status=ValorStatus.SUSPEITO,
            valor_centavos=centavos,
            valor_original=str(valor_raw),
            codigo_erro="VALOR_SUSPEITO",
            mensagem=(
                f"Valor acima do máximo esperado "
                f"(R$ {valor_max_centavos / 100:.2f}). Pode ser erro de vírgula?"
            ),
        )

    return ResultadoValidacaoValor(
        status=ValorStatus.VALIDO,
        valor_centavos=centavos,
        valor_original=str(valor_raw),
        codigo_erro=None,
        mensagem="Valor válido",
    )
