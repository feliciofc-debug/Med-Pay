"""Gerador CNAB 240 — Unicred (banco 136).

Layout próximo do FEBRABAN padrão. Versões e códigos são os do MVP
original (validados com a Unicred Centro-Norte).

Documentação de apoio: docs/CNAB240_UNICRED.md
"""

from __future__ import annotations

from app.services.cnab_base import CNABGeneratorBase


class CNABGeneratorUnicred(CNABGeneratorBase):
    """Gerador específico Unicred — usa layout FEBRABAN puro."""

    CODIGO_BANCO = "136"
    NOME_BANCO = "UNICRED"
    VERSAO_LAYOUT_ARQUIVO = "103"
    VERSAO_LAYOUT_LOTE = "046"
    PREFIXO_NOME_ARQUIVO = "MEDPAG"
    EXTENSAO_NOME_ARQUIVO = "REM"


__all__ = ["CNABGeneratorUnicred"]
