"""Exportação pro RH/folha (modo_pagamento = EXPORT_RH).

Modelo de negócio: hospital público / cliente que NÃO usa CNAB. Em vez
de gerar arquivo bancário, a MedPag entrega um arquivo (CSV ou XLSX) pro
RH do cliente processar a folha no sistema dele (eSocial, folha
municipal, etc.).

A MedPag não paga nem custodia — só organiza os dados validados num
formato que o RH consome. Dados sensíveis (CPF/conta) saem MASCARADOS
por padrão; o desmascaramento exige fluxo auditado de descriptografia.

Reusa `folha_pagamento.gerar_folha_xlsx` quando o caller quer o layout
formal de folha. Aqui o foco é o CSV simples e universal pro RH importar.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime

from app.models.lote import Lote
from app.models.pagamento import Pagamento


@dataclass(slots=True)
class LinhaExportRH:
    cpf: str
    nome: str
    valor_centavos: int
    modalidade: str
    banco: str | None
    agencia: str | None
    conta: str | None
    chave_pix: str | None


# Cabeçalhos do CSV (ordem estável — clientes mapeiam por nome de coluna).
COLUNAS_CSV = [
    "CPF",
    "Nome",
    "Valor (R$)",
    "Modalidade",
    "Banco",
    "Agencia",
    "Conta",
    "Chave PIX",
    "Competencia",
]


def _valor_brl(centavos: int) -> str:
    """123456 -> '1234,56' (formato pt-BR pra Excel/RH)."""
    return f"{centavos / 100:.2f}".replace(".", ",")


def montar_linhas(pagamentos: list[Pagamento]) -> list[LinhaExportRH]:
    """Converte pagamentos do lote em linhas de export (dados mascarados)."""
    linhas: list[LinhaExportRH] = []
    for p in pagamentos:
        linhas.append(
            LinhaExportRH(
                cpf=p.cpf_mascarado or "",
                nome=p.nome,
                valor_centavos=p.valor_centavos,
                modalidade=p.modalidade.value if p.modalidade else "—",
                banco=p.banco_codigo,
                agencia=None,  # agência criptografada — não exporta crua
                conta=p.conta_mascarada,
                chave_pix=p.chave_pix,
            )
        )
    return linhas


def gerar_export_rh_csv(
    *,
    competencia: str,
    pagamentos: list[Pagamento],
) -> bytes:
    """Gera o CSV (pt-BR, separador ';', UTF-8 BOM) pro RH importar."""
    linhas = montar_linhas(pagamentos)

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n")
    writer.writerow(COLUNAS_CSV)
    for linha in linhas:
        writer.writerow(
            [
                linha.cpf,
                linha.nome,
                _valor_brl(linha.valor_centavos),
                linha.modalidade,
                linha.banco or "",
                linha.agencia or "",
                linha.conta or "",
                linha.chave_pix or "",
                competencia,
            ]
        )

    # UTF-8 BOM pro Excel abrir acentuação certa
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def nome_arquivo_export(lote: Lote, *, agora: datetime | None = None) -> str:
    """Nome sugerido pro arquivo de export RH."""
    agora = agora or datetime.now()
    ref = (lote.referencia or "folha").replace("/", "-").replace(" ", "_")
    return f"export_rh_{ref}_{agora:%Y%m%d_%H%M}.csv"


__all__ = [
    "COLUNAS_CSV",
    "LinhaExportRH",
    "gerar_export_rh_csv",
    "montar_linhas",
    "nome_arquivo_export",
]
