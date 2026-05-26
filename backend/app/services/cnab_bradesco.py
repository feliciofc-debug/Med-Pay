"""Gerador CNAB 240 — Bradesco (banco 237).

Particularidades do Bradesco no CNAB 240 Pagamentos:
    - Versão do layout de arquivo: "089"
    - Versão do layout de lote:    "045"
    - Código de convênio (pos 33-52, 20 chars): formato Bradesco
        - posições 1-9:   zeros
        - posições 10-15: ID do convênio fornecido pelo Bradesco
        - posições 16-20: brancos
      Se `empresa.codigo_convenio` for um identificador de até 6 dígitos
      monta nesse formato; se já tiver 20 chars respeita.
    - Câmaras: 018 (TED entre bancos), 700 (DOC < 5k), 000 (mesmo banco).
    - Algumas instâncias do Bradesco preferem extensão .TXT no nome.

Fonte: cartilha pública "CNAB 240 - Pagamentos Diversos" do Bradesco.
Manual oficial vai validar campos específicos da posição livre.
"""

from __future__ import annotations

from app.services.cnab_base import CNABGeneratorBase
from app.services.cnab_utils import fmt_brancos, fmt_num


class CNABGeneratorBradesco(CNABGeneratorBase):
    """Gerador específico Bradesco (banco 237)."""

    CODIGO_BANCO = "237"
    NOME_BANCO = "BCO BRADESCO SA"
    VERSAO_LAYOUT_ARQUIVO = "089"
    VERSAO_LAYOUT_LOTE = "045"
    PREFIXO_NOME_ARQUIVO = "MEDPAGB"  # B de Bradesco
    EXTENSAO_NOME_ARQUIVO = "REM"

    # ------- Convênio Bradesco: 9 zeros + ID(6) + 5 brancos -------

    def _codigo_convenio_20(self) -> str:
        convenio_bruto = (self.empresa.codigo_convenio or "").strip()
        if len(convenio_bruto) == 20:
            return convenio_bruto.upper()

        somente_digitos = "".join(c for c in convenio_bruto if c.isdigit())
        # Se o admin digitou só o ID (até 6 dígitos), monta no padrão
        id_convenio = fmt_num(somente_digitos[-6:] if somente_digitos else "0", 6)
        return ("0" * 9) + id_convenio + fmt_brancos(5)


__all__ = ["CNABGeneratorBradesco"]
