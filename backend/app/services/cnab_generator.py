"""Re-exports do gerador CNAB — preservados pra compatibilidade.

O código que importa `CNABGenerator` antigo continua funcionando, mas
agora é apenas um alias do `CNABGeneratorUnicred`. Recomendamos novos
chamadores usarem `criar_gerador_cnab()` do `cnab_factory.py` para
suportar múltiplos bancos automaticamente.

Mapa de bancos suportados está em `cnab_factory.ADAPTERS`.
"""

from __future__ import annotations

from app.services.cnab_base import (
    DENSIDADE,
    FORMA_LANCAMENTO_CC,
    LARGURA_LINHA,
    TERMINADOR_LINHA,
    TIPO_SERVICO_FOLHA,
    CNABGeneratorBase,
    CNABGeneratorError,
    CNABResult,
)
from app.services.cnab_bradesco import CNABGeneratorBradesco
from app.services.cnab_factory import ADAPTERS, criar_gerador_cnab
from app.services.cnab_itau import CNABGeneratorItau
from app.services.cnab_unicred import CNABGeneratorUnicred

# Alias histórico: o nome "CNABGenerator" sempre se referiu ao gerador
# Unicred (era o único). Mantemos pra não quebrar imports antigos.
CNABGenerator = CNABGeneratorUnicred

# Constantes que existiam no módulo original e podem estar sendo usadas
# em testes ou outros lugares.
CODIGO_BANCO_UNICRED = CNABGeneratorUnicred.CODIGO_BANCO
NOME_BANCO_UNICRED = CNABGeneratorUnicred.NOME_BANCO
VERSAO_LAYOUT_ARQUIVO = CNABGeneratorUnicred.VERSAO_LAYOUT_ARQUIVO
VERSAO_LAYOUT_LOTE = CNABGeneratorUnicred.VERSAO_LAYOUT_LOTE


__all__ = [
    "ADAPTERS",
    "CNABGenerator",
    "CNABGeneratorBase",
    "CNABGeneratorBradesco",
    "CNABGeneratorError",
    "CNABGeneratorItau",
    "CNABGeneratorUnicred",
    "CNABResult",
    "CODIGO_BANCO_UNICRED",
    "DENSIDADE",
    "FORMA_LANCAMENTO_CC",
    "LARGURA_LINHA",
    "NOME_BANCO_UNICRED",
    "TERMINADOR_LINHA",
    "TIPO_SERVICO_FOLHA",
    "VERSAO_LAYOUT_ARQUIVO",
    "VERSAO_LAYOUT_LOTE",
    "criar_gerador_cnab",
]
