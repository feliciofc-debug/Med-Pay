"""API: fechamento de período por hospital.

Endpoints:
    GET  /api/fechamentos                 → lista fechamentos
    GET  /api/fechamentos/preview?ano=&mes=  → preview do mês (não persiste)
    POST /api/fechamentos                 → tranca o período
    GET  /api/fechamentos/{id}            → detalhe de um fechamento
    POST /api/fechamentos/{id}/reabrir    → reabre (só se não virou lote)
    POST /api/fechamentos/{id}/gerar-lote → cria Lote a partir do fechamento
    GET  /api/fechamentos/{id}/extrato.xlsx → baixa extrato consolidado (XLSX)

Permissões:
    - listar / preview / detalhar  → require_visao_executiva (ADMIN, GESTOR, etc)
    - trancar / reabrir / gerar    → require_gestor_hospital (GESTOR + ADMIN + APROVADOR)
"""

from __future__ import annotations

import io
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    get_db,
    get_tenant_id,
    require_gestor_hospital,
    require_visao_executiva,
)
from app.core.exceptions import ValidacaoError
from app.models.user import User
from app.schemas.fechamento import (
    FechamentoListResponse,
    FechamentoOut,
    GerarLoteResponse,
    ReabrirFechamentoResponse,
    TrancarPeriodoRequest,
)
from app.services import fechamento_service

router = APIRouter()


# ============================================================
# Listar / detalhar
# ============================================================


@router.get("", response_model=FechamentoListResponse)
async def listar(
    ano: int | None = Query(default=None, ge=2020, le=2100),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_visao_executiva),
    tenant_id: UUID | None = Depends(get_tenant_id),
) -> FechamentoListResponse:
    """Lista fechamentos do tenant atual.

    Se o usuário for MedPag interno (cliente_id=NULL), lista de TODOS os
    tenants. Se for de hospital, vê só os do próprio hospital.
    """
    fechamentos = await fechamento_service.listar_fechamentos(
        db, cliente_id=tenant_id, ano=ano, limit=limit
    )
    return FechamentoListResponse(
        fechamentos=[FechamentoOut.model_validate(f) for f in fechamentos],
        total=len(fechamentos),
    )


@router.get("/{fechamento_id}", response_model=FechamentoOut)
async def detalhar(
    fechamento_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_visao_executiva),
    tenant_id: UUID | None = Depends(get_tenant_id),
) -> FechamentoOut:
    fechamento = await fechamento_service.obter_fechamento(
        db, fechamento_id, cliente_id=tenant_id
    )
    return FechamentoOut.model_validate(fechamento)


# ============================================================
# Preview (não persiste)
# ============================================================


@router.get("/preview/mes")
async def preview(
    ano: int = Query(..., ge=2020, le=2100),
    mes: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_visao_executiva),
    tenant_id: UUID | None = Depends(get_tenant_id),
):
    """Calcula o que entraria num fechamento da competência sem persistir.

    Tenant precisa estar definido — MedPag interno também precisa
    escolher um cliente_id (via query). Aqui assumimos que MedPag não
    chama esse endpoint sem tenant.
    """
    if tenant_id is None:
        # Sem tenant não dá pra calcular preview.
        return {
            "erro": (
                "Selecione um hospital antes de pré-visualizar o fechamento. "
                "MedPag interno precisa setar tenant pra calcular."
            )
        }

    extrato = await fechamento_service.preview_fechamento(
        db, cliente_id=tenant_id, ano=ano, mes=mes
    )
    # Devolve o ExtratoConsolidado como dict simples
    return {
        "titulo": extrato.titulo,
        "competencia": f"{mes:02d}/{ano}",
        "cliente_id": str(extrato.cliente_id),
        "cliente_nome": extrato.cliente_nome,
        "total_fichas": extrato.total_fichas,
        "total_linhas": extrato.total_linhas,
        "total_medicos_unicos": extrato.total_medicos_unicos,
        "medicos_nao_cadastrados": extrato.medicos_nao_cadastrados,
        "valor_total_centavos": extrato.valor_total_centavos,
        "fichas": [
            {
                "id": str(f.id),
                "nome_arquivo": f.nome_arquivo,
                "status": f.status,
                "qtd_linhas": f.qtd_linhas,
                "valor_total_centavos": f.valor_total_centavos,
                "competencia": f.competencia,
                "coordenador": f.coordenador,
            }
            for f in extrato.fichas
        ],
        "medicos": [
            {
                "cpf_mascarado": m.cpf_mascarado,
                "nome": m.nome,
                "qtd_aparicoes": m.qtd_aparicoes,
                "valor_total_centavos": m.valor_total_centavos,
                "beneficiario_cadastrado": m.beneficiario_cadastrado,
            }
            for m in extrato.medicos
        ],
    }


# ============================================================
# Trancar
# ============================================================


@router.post("", response_model=FechamentoOut, status_code=201)
async def trancar(
    payload: TrancarPeriodoRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_gestor_hospital),
    tenant_id: UUID | None = Depends(get_tenant_id),
) -> FechamentoOut:
    """Tranca um período (cria FechamentoPeriodo TRANCADO).

    Tenant precisa estar definido (MedPag interno tem que escolher um
    hospital antes de trancar — não dá pra trancar "tudo de uma vez").
    """
    if tenant_id is None:
        raise ValidacaoError(
            "MedPag interno precisa escolher um hospital antes de trancar."
        )

    fechamento = await fechamento_service.trancar_periodo(
        db,
        cliente_id=tenant_id,
        ano=payload.ano,
        mes=payload.mes,
        user=user,
        observacoes=payload.observacoes,
    )
    # Recarrega com relacionamentos
    fechamento = await fechamento_service.obter_fechamento(
        db, fechamento.id, cliente_id=tenant_id
    )
    return FechamentoOut.model_validate(fechamento)


# ============================================================
# Reabrir
# ============================================================


@router.post("/{fechamento_id}/reabrir", response_model=ReabrirFechamentoResponse)
async def reabrir(
    fechamento_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_gestor_hospital),
    tenant_id: UUID | None = Depends(get_tenant_id),
) -> ReabrirFechamentoResponse:
    fechamento = await fechamento_service.reabrir_periodo(
        db, fechamento_id=fechamento_id, user=user, cliente_id=tenant_id
    )
    return ReabrirFechamentoResponse(
        fechamento=FechamentoOut.model_validate(fechamento)
    )


# ============================================================
# Gerar lote a partir do fechamento
# ============================================================


@router.post("/{fechamento_id}/gerar-lote", response_model=GerarLoteResponse)
async def gerar_lote(
    fechamento_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_gestor_hospital),
    tenant_id: UUID | None = Depends(get_tenant_id),
) -> GerarLoteResponse:
    fechamento, lote = await fechamento_service.gerar_lote_do_fechamento(
        db, fechamento_id=fechamento_id, user=user, cliente_id=tenant_id
    )
    return GerarLoteResponse(
        fechamento=FechamentoOut.model_validate(fechamento),
        lote_id=lote.id,
    )


# ============================================================
# Download do extrato (XLSX)
# ============================================================


def _gerar_xlsx_extrato(
    *,
    titulo: str,
    cliente_nome: str,
    competencia: str,
    fechamento_id: str,
    medicos: list,
    fichas: list,
    valor_total_centavos: int,
    qtd_fichas: int,
    qtd_medicos: int,
) -> bytes:
    """Gera planilha XLSX com o extrato consolidado pro contador/RH."""
    wb = Workbook()
    ws_cap = wb.active
    ws_cap.title = "Resumo"

    bold = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="1F3A5F")
    header_font = Font(bold=True, color="FFFFFF")

    ws_cap["A1"] = "EXTRATO DE FECHAMENTO"
    ws_cap["A1"].font = Font(bold=True, size=14)
    ws_cap.merge_cells("A1:D1")

    ws_cap["A3"] = "Hospital:"
    ws_cap["A3"].font = bold
    ws_cap["B3"] = cliente_nome
    ws_cap["A4"] = "Competência:"
    ws_cap["A4"].font = bold
    ws_cap["B4"] = competencia
    ws_cap["A5"] = "Fechamento ID:"
    ws_cap["A5"].font = bold
    ws_cap["B5"] = fechamento_id

    ws_cap["A7"] = "Total de fichas:"
    ws_cap["A7"].font = bold
    ws_cap["B7"] = qtd_fichas
    ws_cap["A8"] = "Médicos distintos:"
    ws_cap["A8"].font = bold
    ws_cap["B8"] = qtd_medicos
    ws_cap["A9"] = "Valor total:"
    ws_cap["A9"].font = bold
    valor_reais = valor_total_centavos / 100
    ws_cap["B9"] = f"R$ {valor_reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    ws_cap.column_dimensions["A"].width = 22
    ws_cap.column_dimensions["B"].width = 50

    # ---------- Aba Médicos ----------
    ws = wb.create_sheet("Médicos")
    headers = ["CPF", "Nome", "Plantões", "Valor (R$)", "Cadastrado?"]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for row_idx, m in enumerate(medicos, 2):
        valor = m.valor_total_centavos / 100
        ws.cell(row=row_idx, column=1, value=m.cpf_mascarado)
        ws.cell(row=row_idx, column=2, value=m.nome)
        ws.cell(row=row_idx, column=3, value=m.qtd_aparicoes)
        cell_v = ws.cell(row=row_idx, column=4, value=valor)
        cell_v.number_format = "#,##0.00"
        ws.cell(
            row=row_idx,
            column=5,
            value="✓" if m.beneficiario_cadastrado else "—",
        )

    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 35
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 14
    ws.column_dimensions["E"].width = 12

    # ---------- Aba Fichas ----------
    ws_f = wb.create_sheet("Fichas")
    headers_f = [
        "Arquivo",
        "Competência",
        "Coordenador",
        "Linhas",
        "Valor (R$)",
        "Status",
    ]
    for col_idx, h in enumerate(headers_f, 1):
        cell = ws_f.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for row_idx, f in enumerate(fichas, 2):
        valor = f.valor_total_centavos / 100
        ws_f.cell(row=row_idx, column=1, value=f.nome_arquivo)
        ws_f.cell(row=row_idx, column=2, value=f.competencia or "—")
        ws_f.cell(row=row_idx, column=3, value=f.coordenador or "—")
        ws_f.cell(row=row_idx, column=4, value=f.qtd_linhas)
        cell_v = ws_f.cell(row=row_idx, column=5, value=valor)
        cell_v.number_format = "#,##0.00"
        ws_f.cell(row=row_idx, column=6, value=f.status)

    ws_f.column_dimensions["A"].width = 40
    ws_f.column_dimensions["B"].width = 12
    ws_f.column_dimensions["C"].width = 25
    ws_f.column_dimensions["D"].width = 8
    ws_f.column_dimensions["E"].width = 14
    ws_f.column_dimensions["F"].width = 12

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


@router.get("/{fechamento_id}/folha.xlsx")
async def baixar_folha_xlsx(
    fechamento_id: UUID,
    aplicar_irrf: bool = Query(
        default=False,
        description="Se True, calcula IRRF retido na fonte (Tabela RFB 2026)",
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_visao_executiva),
    tenant_id: UUID | None = Depends(get_tenant_id),
) -> Response:
    """Baixa folha de pagamento em XLSX (formato formal pro contador/RH)."""
    from datetime import datetime

    from app.services import consolidacao_service, folha_pagamento

    fechamento = await fechamento_service.obter_fechamento(
        db, fechamento_id, cliente_id=tenant_id
    )
    cliente_nome = fechamento.cliente.nome if fechamento.cliente else "Hospital"
    competencia = f"{fechamento.mes:02d}/{fechamento.ano}"

    extrato = await consolidacao_service.consolidar_por_hospital_mes(
        db, cliente_id=fechamento.cliente_id, competencia=competencia
    )

    linhas = folha_pagamento.montar_linhas_folha(
        extrato.medicos, aplicar_irrf=aplicar_irrf
    )
    linhas = await folha_pagamento.enriquecer_com_dados_bancarios(
        db, linhas, extrato.medicos
    )

    xlsx = folha_pagamento.gerar_folha_xlsx(
        cliente_nome=cliente_nome,
        competencia=competencia,
        fechamento_id=str(fechamento.id),
        linhas=linhas,
        aplicar_irrf=aplicar_irrf,
        gerado_em=datetime.utcnow(),
    )

    filename = (
        f"folha-{cliente_nome.replace(' ', '_').lower()}-"
        f"{fechamento.ano}-{fechamento.mes:02d}.xlsx"
    )
    return Response(
        content=xlsx,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{fechamento_id}/folha.pdf")
async def baixar_folha_pdf(
    fechamento_id: UUID,
    aplicar_irrf: bool = Query(
        default=False,
        description="Se True, calcula IRRF retido na fonte (Tabela RFB 2026)",
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_visao_executiva),
    tenant_id: UUID | None = Depends(get_tenant_id),
) -> Response:
    """Baixa folha de pagamento em PDF (documento assinavel pro hospital/contador)."""
    from datetime import datetime

    from app.services import consolidacao_service, folha_pagamento

    fechamento = await fechamento_service.obter_fechamento(
        db, fechamento_id, cliente_id=tenant_id
    )
    cliente_nome = fechamento.cliente.nome if fechamento.cliente else "Hospital"
    competencia = f"{fechamento.mes:02d}/{fechamento.ano}"

    extrato = await consolidacao_service.consolidar_por_hospital_mes(
        db, cliente_id=fechamento.cliente_id, competencia=competencia
    )

    linhas = folha_pagamento.montar_linhas_folha(
        extrato.medicos, aplicar_irrf=aplicar_irrf
    )
    linhas = await folha_pagamento.enriquecer_com_dados_bancarios(
        db, linhas, extrato.medicos
    )

    pdf = folha_pagamento.gerar_folha_pdf(
        cliente_nome=cliente_nome,
        competencia=competencia,
        fechamento_id=str(fechamento.id),
        linhas=linhas,
        aplicar_irrf=aplicar_irrf,
        gerado_em=datetime.utcnow(),
    )

    filename = (
        f"folha-{cliente_nome.replace(' ', '_').lower()}-"
        f"{fechamento.ano}-{fechamento.mes:02d}.pdf"
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{fechamento_id}/extrato.xlsx")
async def baixar_extrato_xlsx(
    fechamento_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_visao_executiva),
    tenant_id: UUID | None = Depends(get_tenant_id),
) -> Response:
    """Baixa o extrato consolidado deste fechamento em XLSX.

    Calcula em tempo real (re-roda consolidar_por_hospital_mes pro
    mesmo período). Como o fechamento congela as fichas no metadados,
    o cálculo segue refletindo o snapshot.
    """
    from app.services import consolidacao_service

    fechamento = await fechamento_service.obter_fechamento(
        db, fechamento_id, cliente_id=tenant_id
    )

    cliente_nome = fechamento.cliente.nome if fechamento.cliente else "Hospital"
    competencia = f"{fechamento.mes:02d}/{fechamento.ano}"

    # Re-roda a consolidação pra ter os dados de medicos/fichas frescos.
    # Como após trancar as fichas continuam EXTRAIDA/REVISADA, isso ainda
    # bate com o snapshot (a menos que tenha gerado lote — aí virou CONVERTIDA
    # e o consolidador ignora). Para simplicidade do MVP, usamos os snapshots.
    extrato = await consolidacao_service.consolidar_por_hospital_mes(
        db, cliente_id=fechamento.cliente_id, competencia=competencia
    )

    xlsx = _gerar_xlsx_extrato(
        titulo=extrato.titulo,
        cliente_nome=cliente_nome,
        competencia=competencia,
        fechamento_id=str(fechamento.id),
        medicos=extrato.medicos,
        fichas=extrato.fichas,
        valor_total_centavos=fechamento.total_centavos,
        qtd_fichas=fechamento.qtd_fichas,
        qtd_medicos=fechamento.qtd_medicos,
    )

    filename = (
        f"extrato-{cliente_nome.replace(' ', '_').lower()}-"
        f"{fechamento.ano}-{fechamento.mes:02d}.xlsx"
    )
    return Response(
        content=xlsx,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
