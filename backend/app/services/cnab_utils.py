"""Utilitários para formatação de campos CNAB 240.

CNAB exige formatação ESTRITA:
- Numéricos: zero à esquerda, alinhado à direita, sem separadores
- Alfanuméricos: maiúsculas, sem acentos, alinhado à esquerda, espaços
- Sem CR/LF interno, cada linha tem exatamente 240 caracteres
- Datas: DDMMAAAA. Horas: HHMMSS.

Tudo aqui é puro e testável isoladamente.
"""

from __future__ import annotations

import unicodedata
from datetime import date, datetime


def remover_acentos(texto: str) -> str:
    """JOSÉ → JOSE, açúcar → acucar."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def fmt_alfa(valor: str | None, tamanho: int) -> str:
    """Formata campo alfanumérico: maiúsculas, sem acentos, espaços à direita.

    Trunca se exceder, preenche com espaço se faltar.
    """
    if valor is None:
        valor = ""
    s = remover_acentos(str(valor)).upper()
    # Substitui caracteres incompatíveis com latin-1 por espaço
    s = "".join(c if c.isascii() or c == " " else " " for c in s)
    return s.ljust(tamanho)[:tamanho]


def fmt_num(valor: int | str | None, tamanho: int) -> str:
    """Formata campo numérico: zero à esquerda, alinhado à direita.

    Aceita int (preferido), str de dígitos. Filtra não-dígitos por segurança.
    Trunca os dígitos mais à esquerda se exceder (não deveria acontecer).
    """
    if valor is None:
        valor = 0
    if isinstance(valor, int):
        s = str(valor)
    else:
        s = "".join(c for c in str(valor) if c.isdigit()) or "0"
    return s.zfill(tamanho)[-tamanho:]


def fmt_data(d: date | datetime | None) -> str:
    """Data no formato DDMMAAAA (8 chars). None vira zeros."""
    if d is None:
        return "0" * 8
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%d%m%Y")


def fmt_hora(d: datetime | None) -> str:
    """Hora no formato HHMMSS (6 chars). None vira zeros."""
    if d is None:
        return "0" * 6
    return d.strftime("%H%M%S")


def fmt_brancos(tamanho: int) -> str:
    """Espaços em branco do tamanho dado (filler)."""
    return " " * tamanho


def fmt_zeros(tamanho: int) -> str:
    """Zeros do tamanho dado (filler numérico)."""
    return "0" * tamanho


def calcular_dv_modulo11(numero: str, pesos: list[int] | None = None) -> str:
    """Calcula DV pelo módulo 11 padrão FEBRABAN.

    Args:
        numero: dígitos para calcular DV
        pesos: lista de pesos (default: 2..9 ciclando da direita pra esquerda)

    Returns:
        Dígito verificador como char ('0'-'9' ou 'X' se resto = 1)

    Nota: o algoritmo exato da Unicred pra agência+conta deve ser
    confirmado com o manual oficial deles antes de produção.
    """
    if not numero or not numero.isdigit():
        return "0"

    if pesos is None:
        pesos = [2, 3, 4, 5, 6, 7, 8, 9]

    soma = 0
    for i, digito in enumerate(reversed(numero)):
        peso = pesos[i % len(pesos)]
        soma += int(digito) * peso

    resto = soma % 11
    if resto == 0 or resto == 1:
        return "0"
    dv = 11 - resto
    return "X" if dv == 10 else str(dv)


__all__ = [
    "calcular_dv_modulo11",
    "fmt_alfa",
    "fmt_brancos",
    "fmt_data",
    "fmt_hora",
    "fmt_num",
    "fmt_zeros",
    "remover_acentos",
]
