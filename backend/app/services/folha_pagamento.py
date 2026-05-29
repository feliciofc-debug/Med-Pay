"""Geracao de folha de pagamento a partir de um FechamentoPeriodo.

Diferenca pro extrato consolidado (XLSX/Resumo):

- Extrato = visao operacional pro gestor ver as fichas/medicos
- Folha de pagamento = documento FORMAL pro contador / RH anexar
  no eSocial, holerite ou processo de folha do hospital

A folha apresenta:
- CPF completo (formatado, sem mascarar)
- Nome completo do prestador
- Valor bruto, base de calculo
- IRRF retido na fonte (opcional, configuravel)
- Valor liquido
- Modalidade de pagamento (PIX/TED)
- Dados bancarios (caso TED) ou chave PIX (caso PIX)
- Totalizadores no fim

IRRF (Tabela 2025/2026 para Pessoa Fisica autonoma):
    Base de calculo (R$)            Aliquota   Parc. a deduzir
    Ate 2.259,20                    Isento     -
    De 2.259,21 ate 2.826,65        7,5%       R$ 169,44
    De 2.826,66 ate 3.751,05        15%        R$ 381,44
    De 3.751,06 ate 4.664,68        22,5%      R$ 662,77
    Acima de 4.664,68               27,5%      R$ 896,00

Importante: como medico autonomo NORMALMENTE emite RPA / faz GPS
proprio, o IRRF aqui e' opcional e o hospital decide caso a caso
se retem na fonte ou nao. Esta logica e' uma facilidade — nao
substitui a orientacao do contador.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.beneficiario import Beneficiario
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


# ============================================================
# IRRF
# ============================================================


@dataclass(slots=True)
class FaixaIRRF:
    limite_superior: Decimal  # R$
    aliquota: Decimal          # 0..1
    parcela_deduzir: Decimal   # R$


TABELA_IRRF_2026: list[FaixaIRRF] = [
    FaixaIRRF(Decimal("2259.20"), Decimal("0.000"), Decimal("0.00")),
    FaixaIRRF(Decimal("2826.65"), Decimal("0.075"), Decimal("169.44")),
    FaixaIRRF(Decimal("3751.05"), Decimal("0.150"), Decimal("381.44")),
    FaixaIRRF(Decimal("4664.68"), Decimal("0.225"), Decimal("662.77")),
    FaixaIRRF(Decimal("9999999"), Decimal("0.275"), Decimal("896.00")),
]


def calcular_irrf(valor_bruto_centavos: int) -> int:
    """Retorna o IRRF a reter em centavos."""
    valor = Decimal(valor_bruto_centavos) / Decimal("100")
    for faixa in TABELA_IRRF_2026:
        if valor <= faixa.limite_superior:
            irrf = (valor * faixa.aliquota) - faixa.parcela_deduzir
            irrf_arred = irrf.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if irrf_arred < 0:
                return 0
            return int(irrf_arred * 100)
    return 0


# ============================================================
# Formatacao
# ============================================================


def _formatar_cpf(cpf: str) -> str:
    """Formata CPF se tiver 11 digitos; senao devolve como veio (mascarado)."""
    if not cpf:
        return "—"
    so_dig = "".join(c for c in cpf if c.isdigit())
    if len(so_dig) == 11:
        return f"{so_dig[:3]}.{so_dig[3:6]}.{so_dig[6:9]}-{so_dig[9:]}"
    # CPF ja mascarado (ex: ***.123.456-**) ou parcial — devolve como veio
    return cpf


def _formatar_brl(centavos: int) -> str:
    """123456 -> 'R$ 1.234,56'"""
    reais = centavos / 100
    return f"R$ {reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _competencia_extenso(ano: int, mes: int) -> str:
    meses = [
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ]
    return f"{meses[mes - 1].capitalize()}/{ano}"


# ============================================================
# Modelo de linha da folha
# ============================================================


@dataclass(slots=True)
class LinhaFolha:
    cpf: str                    # so digitos
    nome: str
    valor_bruto_centavos: int
    irrf_centavos: int
    valor_liquido_centavos: int
    modalidade: str             # 'PIX' ou 'TED'
    banco: str | None
    agencia: str | None
    conta: str | None
    chave_pix: str | None
    qtd_plantoes: int


def montar_linhas_folha(
    medicos: list[Any],
    *,
    aplicar_irrf: bool = False,
) -> list[LinhaFolha]:
    """Converte lista de MedicoNoExtrato em linhas de folha.

    O cpf chega ja mascarado (ex: '***.123.456-**'). Mantemos como veio
    pra nao expor dado sensivel na folha — dados completos exigem fluxo
    de descriptografia auditado.

    Caller deve depois chamar `enriquecer_com_dados_bancarios` pra
    preencher modalidade/banco/conta/pix.
    """
    linhas: list[LinhaFolha] = []
    for m in medicos:
        bruto = m.valor_total_centavos
        irrf = calcular_irrf(bruto) if aplicar_irrf else 0
        liquido = bruto - irrf
        linhas.append(
            LinhaFolha(
                cpf=m.cpf_mascarado or "",
                nome=m.nome,
                valor_bruto_centavos=bruto,
                irrf_centavos=irrf,
                valor_liquido_centavos=liquido,
                modalidade="—",
                banco=None,
                agencia=None,
                conta=None,
                chave_pix=None,
                qtd_plantoes=m.qtd_aparicoes,
            )
        )
    return linhas


async def enriquecer_com_dados_bancarios(
    db: AsyncSession,
    linhas: list[LinhaFolha],
    medicos_extrato: list[Any],
) -> list[LinhaFolha]:
    """Faz lookup nos beneficiarios pra preencher banco/conta/PIX.

    Usa `beneficiario_id` do MedicoNoExtrato quando disponivel (medico
    ja cadastrado). Quando nao tem beneficiario_id, a linha fica
    sem dados bancarios — sinaliza pro contador que esse medico
    precisa ser cadastrado.

    Os campos `_mascarada` sao usados pra preservar dados sensiveis
    (a folha exibe '****1234' em vez do numero completo).
    """
    benef_ids = [
        m.beneficiario_id for m in medicos_extrato if m.beneficiario_id is not None
    ]
    if not benef_ids:
        return linhas

    q = select(Beneficiario).where(Beneficiario.id.in_(benef_ids))
    result = await db.execute(q)
    beneficiarios = {b.id: b for b in result.scalars()}

    for idx, m in enumerate(medicos_extrato):
        if idx >= len(linhas):
            break
        if m.beneficiario_id is None:
            continue
        b = beneficiarios.get(m.beneficiario_id)
        if b is None:
            continue
        linha = linhas[idx]
        if b.pix_chave_mascarada:
            linha.modalidade = "PIX"
            linha.chave_pix = b.pix_chave_mascarada
        elif b.banco_codigo and b.conta_mascarada:
            linha.modalidade = "TED"
            linha.banco = b.banco_codigo
            linha.agencia = b.agencia_mascarada
            linha.conta = b.conta_mascarada

    return linhas


# ============================================================
# Gerador de XLSX (formato folha)
# ============================================================


def gerar_folha_xlsx(
    *,
    cliente_nome: str,
    competencia: str,
    fechamento_id: str,
    linhas: list[LinhaFolha],
    aplicar_irrf: bool,
    gerado_em: datetime,
) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Folha"

    header_fill = PatternFill("solid", fgColor="1F3A5F")
    header_font = Font(bold=True, color="FFFFFF", size=10)
    bold = Font(bold=True, size=10)
    total_fill = PatternFill("solid", fgColor="F1F5F9")
    thin = Side(style="thin", color="CBD5E1")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # Cabecalho informativo
    ws["A1"] = "FOLHA DE PAGAMENTO DE PRESTADORES"
    ws["A1"].font = Font(bold=True, size=14)
    ws.merge_cells("A1:H1")

    ws["A3"] = "Hospital:"
    ws["A3"].font = bold
    ws["B3"] = cliente_nome
    ws["A4"] = "Competência:"
    ws["A4"].font = bold
    ws["B4"] = competencia
    ws["A5"] = "Documento:"
    ws["A5"].font = bold
    ws["B5"] = f"Fechamento {fechamento_id[:8]}"
    ws["A6"] = "Gerado em:"
    ws["A6"].font = bold
    ws["B6"] = gerado_em.strftime("%d/%m/%Y %H:%M")
    ws["A7"] = "IRRF:"
    ws["A7"].font = bold
    ws["B7"] = (
        "Aplicado (Tabela RFB 2026)" if aplicar_irrf else "Não aplicado"
    )

    # Cabecalho da tabela
    linha_header = 9
    headers = [
        "Nº",
        "CPF",
        "Nome do Prestador",
        "Plantões",
        "Valor Bruto",
        "IRRF",
        "Valor Líquido",
        "Observação",
    ]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=linha_header, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    # Linhas
    total_bruto = 0
    total_irrf = 0
    total_liquido = 0
    for idx, linha in enumerate(linhas, 1):
        row = linha_header + idx
        ws.cell(row=row, column=1, value=idx).border = border
        ws.cell(row=row, column=2, value=_formatar_cpf(linha.cpf)).border = border
        ws.cell(row=row, column=3, value=linha.nome).border = border
        ws.cell(row=row, column=4, value=linha.qtd_plantoes).border = border
        c_bruto = ws.cell(row=row, column=5, value=linha.valor_bruto_centavos / 100)
        c_bruto.number_format = "#,##0.00"
        c_bruto.border = border
        c_irrf = ws.cell(row=row, column=6, value=linha.irrf_centavos / 100)
        c_irrf.number_format = "#,##0.00"
        c_irrf.border = border
        c_liq = ws.cell(row=row, column=7, value=linha.valor_liquido_centavos / 100)
        c_liq.number_format = "#,##0.00"
        c_liq.font = bold
        c_liq.border = border
        obs = "—"
        if linha.chave_pix:
            obs = f"PIX: {linha.chave_pix}"
        elif linha.banco:
            obs = f"{linha.banco} Ag {linha.agencia or '—'} CC {linha.conta or '—'}"
        ws.cell(row=row, column=8, value=obs).border = border

        total_bruto += linha.valor_bruto_centavos
        total_irrf += linha.irrf_centavos
        total_liquido += linha.valor_liquido_centavos

    # Linha total
    total_row = linha_header + len(linhas) + 1
    c = ws.cell(row=total_row, column=3, value="TOTAL")
    c.font = bold
    c.alignment = Alignment(horizontal="right")
    c.fill = total_fill
    for col in (5, 6, 7):
        ws.cell(row=total_row, column=col).fill = total_fill
        ws.cell(row=total_row, column=col).font = bold
    ws.cell(row=total_row, column=5, value=total_bruto / 100).number_format = "#,##0.00"
    ws.cell(row=total_row, column=6, value=total_irrf / 100).number_format = "#,##0.00"
    ws.cell(row=total_row, column=7, value=total_liquido / 100).number_format = "#,##0.00"
    ws.cell(row=total_row, column=4, value=sum(linha.qtd_plantoes for linha in linhas))
    ws.cell(row=total_row, column=4).font = bold
    ws.cell(row=total_row, column=4).fill = total_fill

    # Larguras
    widths = {"A": 5, "B": 16, "C": 38, "D": 10, "E": 14, "F": 12, "G": 14, "H": 35}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    # Rodape: assinaturas
    sig_row = total_row + 4
    ws.cell(row=sig_row, column=2, value="_" * 40)
    ws.cell(row=sig_row + 1, column=2, value="Gestor do hospital")
    ws.cell(row=sig_row + 1, column=2).font = bold
    ws.cell(row=sig_row, column=6, value="_" * 40)
    ws.cell(row=sig_row + 1, column=6, value="Financeiro / RH")
    ws.cell(row=sig_row + 1, column=6).font = bold

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ============================================================
# Gerador de PDF (formato folha)
# ============================================================


def gerar_folha_pdf(
    *,
    cliente_nome: str,
    competencia: str,
    fechamento_id: str,
    linhas: list[LinhaFolha],
    aplicar_irrf: bool,
    gerado_em: datetime,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"Folha {competencia}",
        author="Med-Pay",
    )

    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle(
        "TituloDoc",
        parent=styles["Heading1"],
        fontSize=16,
        alignment=1,  # center
        spaceAfter=6,
        textColor=colors.HexColor("#1F3A5F"),
    )
    sub_style = ParagraphStyle(
        "Sub",
        parent=styles["Normal"],
        fontSize=10,
        alignment=1,
        textColor=colors.HexColor("#475569"),
        spaceAfter=12,
    )
    info_style = ParagraphStyle(
        "Info",
        parent=styles["Normal"],
        fontSize=9,
        spaceAfter=4,
    )

    elements: list[Any] = []
    elements.append(
        Paragraph("FOLHA DE PAGAMENTO DE PRESTADORES", titulo_style)
    )
    elements.append(
        Paragraph(
            f"{cliente_nome} &nbsp;·&nbsp; Competência {competencia}",
            sub_style,
        )
    )

    elements.append(
        Paragraph(
            f"<b>Documento:</b> Fechamento {fechamento_id[:8]} &nbsp;&nbsp;"
            f"<b>Gerado em:</b> {gerado_em.strftime('%d/%m/%Y %H:%M')} &nbsp;&nbsp;"
            f"<b>IRRF:</b> {'Aplicado (Tabela RFB 2026)' if aplicar_irrf else 'Não aplicado'}",
            info_style,
        )
    )
    elements.append(Spacer(1, 8))

    # Tabela
    headers = [
        "Nº",
        "CPF",
        "Nome",
        "Plantões",
        "Bruto (R$)",
        "IRRF (R$)",
        "Líquido (R$)",
        "Observação",
    ]
    dados: list[list[Any]] = [headers]

    total_bruto = 0
    total_irrf = 0
    total_liquido = 0
    for idx, l in enumerate(linhas, 1):
        obs = "—"
        if l.chave_pix:
            obs = f"PIX: {l.chave_pix}"
        elif l.banco:
            obs = f"{l.banco} Ag {l.agencia or '—'} CC {l.conta or '—'}"
        dados.append(
            [
                str(idx),
                _formatar_cpf(l.cpf),
                l.nome,
                str(l.qtd_plantoes),
                _formatar_brl(l.valor_bruto_centavos),
                _formatar_brl(l.irrf_centavos),
                _formatar_brl(l.valor_liquido_centavos),
                obs,
            ]
        )
        total_bruto += l.valor_bruto_centavos
        total_irrf += l.irrf_centavos
        total_liquido += l.valor_liquido_centavos

    # Linha total
    dados.append(
        [
            "",
            "",
            "TOTAL",
            str(sum(l.qtd_plantoes for l in linhas)),
            _formatar_brl(total_bruto),
            _formatar_brl(total_irrf),
            _formatar_brl(total_liquido),
            "",
        ]
    )

    col_widths = [1 * cm, 3 * cm, 6 * cm, 1.6 * cm, 2.5 * cm, 2.2 * cm, 2.7 * cm, 7 * cm]
    tabela = Table(dados, repeatRows=1, colWidths=col_widths)
    tabela.setStyle(
        TableStyle(
            [
                # Header
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                # Corpo
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAFC")]),
                ("ALIGN", (3, 1), (3, -1), "CENTER"),    # plantoes
                ("ALIGN", (4, 1), (6, -1), "RIGHT"),     # valores
                ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                # Total
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F1F5F9")),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("ALIGN", (2, -1), (2, -1), "RIGHT"),
            ]
        )
    )
    elements.append(tabela)

    elements.append(Spacer(1, 30))

    # Assinaturas
    sig_data = [
        ["_" * 35, "", "_" * 35],
        ["Gestor do hospital", "", "Financeiro / RH"],
    ]
    sig = Table(sig_data, colWidths=[9 * cm, 4 * cm, 9 * cm])
    sig.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTSIZE", (0, 1), (-1, 1), 8),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ]
        )
    )
    elements.append(sig)

    elements.append(Spacer(1, 20))
    elements.append(
        Paragraph(
            "<i>Documento gerado automaticamente pela plataforma Med-Pay. "
            "A retenção de IRRF (quando aplicada) usa a Tabela RFB 2026. "
            "Confirme com seu contador antes de aplicar.</i>",
            ParagraphStyle(
                "Foot",
                parent=styles["Normal"],
                fontSize=7,
                alignment=1,
                textColor=colors.HexColor("#94A3B8"),
            ),
        )
    )

    doc.build(elements)
    buf.seek(0)
    return buf.read()
