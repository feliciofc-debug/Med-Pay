"""Gerador CNAB 240 — Itaú Unibanco (banco 341).

Particularidades do Itaú no CNAB 240 Pagamentos (folha):
    - Versão do layout de arquivo: "040"
    - Versão do layout de lote:    "030"
    - Código de convênio (pos 33-52, 20 chars): formato típico
        - posições 1-8:   convênio (zero à esquerda se < 8)
        - posições 9-12:  agência
        - posições 13-18: conta corrente
        - posições 19-20: DV (conta)
      O MedPag preenche aproveitando `empresa.codigo_convenio` se ele
      tiver formato pronto, ou monta a partir da conta da empresa.
    - Câmara de compensação para créditos: 018 (TED) entre bancos
      e 700 para DOC abaixo de 5k. Para mesmo banco usa 000.

Fonte principal: cartilha pública "Layout CNAB 240 - Pagamentos"
publicada pelo Itaú. Manual oficial confirmará particularidades.
"""

from __future__ import annotations

from app.services.cnab_base import CNABGeneratorBase
from app.services.cnab_utils import fmt_alfa, fmt_num


class CNABGeneratorItau(CNABGeneratorBase):
    """Gerador específico Itaú (banco 341)."""

    CODIGO_BANCO = "341"
    NOME_BANCO = "BANCO ITAU SA"
    VERSAO_LAYOUT_ARQUIVO = "040"
    VERSAO_LAYOUT_LOTE = "030"
    PREFIXO_NOME_ARQUIVO = "MEDPAGI"  # I de Itaú — ajuda triagem
    EXTENSAO_NOME_ARQUIVO = "REM"

    # ------- Convênio Itaú: convenio(8) + agencia(4) + conta(6) + DV(2) -------

    def _codigo_convenio_20(self) -> str:
        """Itaú espera 20 chars: convênio (8) + ag (4) + conta (6) + DV (2).

        Se `empresa.codigo_convenio` já vier com 20 chars (ex.: o admin
        digitou exatamente assim), respeita. Senão monta a partir da
        agência/conta da empresa pagadora.
        """
        convenio_bruto = (self.empresa.codigo_convenio or "").strip()
        if len(convenio_bruto) == 20:
            return convenio_bruto.upper()

        # Sintetiza a partir dos campos da empresa
        agencia, _, conta, conta_dv = self._conta_pagadora()
        convenio_num = "".join(c for c in convenio_bruto if c.isdigit()).zfill(8)[-8:]
        ag_4 = fmt_num(agencia, 4)
        # Conta Itaú tradicional tem 5-6 dígitos significativos
        conta_6 = "".join(c for c in conta if c.isdigit()).zfill(6)[-6:]
        dv_2 = fmt_alfa(conta_dv, 2)
        return convenio_num + ag_4 + conta_6 + dv_2


__all__ = ["CNABGeneratorItau"]
