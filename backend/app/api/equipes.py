"""Rotas REST do módulo Equipe Flex.

Fluxo da operação (caso Hospital do Cérebro / Sandro):
    GET    /api/equipes                       → lista equipes
    POST   /api/equipes                       → cria equipe
    GET    /api/equipes/{id}                  → detalhe + membros
    PUT    /api/equipes/{id}                  → edita equipe
    DELETE /api/equipes/{id}                  → remove (cascata de fechamentos)

    POST   /api/equipes/{id}/membros          → adiciona membro
    PUT    /api/equipes/{id}/membros/{mid}    → edita membro
    DELETE /api/equipes/{id}/membros/{mid}    → remove membro

    POST   /api/equipes/fechamento            → simula OU confirma fechamento
                                                (gera lote se confirmar=True)
    GET    /api/equipes/{id}/fechamentos      → lista fechamentos da equipe
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from uuid import UUID

import pandas as pd
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import (
    get_current_user,
    get_db,
    require_admin,
    require_aprovador,
)
from app.core.exceptions import (
    PermissaoNegadaError,
    ValidacaoError,
)


def _nao_encontrado(msg: str) -> HTTPException:
    return HTTPException(status_code=404, detail=msg)
from app.models.cliente import Cliente
from app.models.contrato_hospital import ContratoHospital, ModoCobranca
from app.models.equipe_flex import EquipeFlex, FechamentoEquipe, MembroEquipe
from app.models.user import User, UserRole
from app.schemas.equipe import (
    EquipeIn,
    EquipeOut,
    FechamentoIn,
    FechamentoOut,
    MembroEquipeIn,
    MembroEquipeOut,
)

log = structlog.get_logger()
router = APIRouter()


# ============================================================
# Helpers
# ============================================================


async def _carregar_equipe(db: AsyncSession, equipe_id: UUID) -> EquipeFlex:
    q = await db.execute(
        select(EquipeFlex)
        .where(EquipeFlex.id == equipe_id)
        .options(selectinload(EquipeFlex.membros))
    )
    eq = q.scalar_one_or_none()
    if eq is None:
        raise _nao_encontrado("Equipe não encontrada")
    return eq


def _equipe_para_out(eq: EquipeFlex) -> EquipeOut:
    membros = sorted(eq.membros, key=lambda m: m.nome.lower())
    return EquipeOut(
        id=eq.id,
        cliente={
            "id": eq.cliente.id,
            "nome": eq.cliente.nome,
            "cnpj": eq.cliente.cnpj,
        },
        nome=eq.nome,
        categoria=eq.categoria,
        valor_hora_centavos=eq.valor_hora_centavos,
        ativa=eq.ativa,
        observacoes=eq.observacoes,
        qtd_membros=len(membros),
        qtd_membros_ativos=sum(1 for m in membros if m.ativo),
        membros=[MembroEquipeOut.model_validate(m) for m in membros],
        created_at=eq.created_at,
    )


async def _verificar_acesso(equipe: EquipeFlex, user: User) -> None:
    """Coordenador só vê equipes mas não edita.

    Pra simplificar, qualquer usuário autenticado pode ver as equipes.
    Edição (criar/editar/deletar) exige role >= APROVADOR.
    """
    if user.role == UserRole.COORDENADOR:
        # Coordenador pode listar/ler — checagem específica é feita por endpoint
        return


def _pegar_pct_medpag_bp(contrato: ContratoHospital | None) -> int:
    """Retorna o % MedPag em basis points conforme o modo de cobrança.

    - PERCENTUAL_REPASSE: usa percentual_volume_bp do contrato
    - MENSALIDADE_SAAS:  retorna 0 (100% vai pros médicos)
    - sem contrato:      retorna 0
    """
    if contrato is None:
        return 0
    if contrato.modo_cobranca == ModoCobranca.MENSALIDADE_SAAS:
        return 0
    return contrato.percentual_volume_bp or 0


# ============================================================
# CRUD Equipes
# ============================================================


@router.get("", response_model=list[EquipeOut])
async def listar_equipes(
    cliente_id: UUID | None = None,
    apenas_ativas: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[EquipeOut]:
    stmt = (
        select(EquipeFlex)
        .options(selectinload(EquipeFlex.membros))
        .order_by(EquipeFlex.nome)
    )
    if cliente_id:
        stmt = stmt.where(EquipeFlex.cliente_id == cliente_id)
    if apenas_ativas:
        stmt = stmt.where(EquipeFlex.ativa.is_(True))

    res = await db.execute(stmt)
    equipes = list(res.scalars().all())
    return [_equipe_para_out(eq) for eq in equipes]


@router.post(
    "",
    response_model=EquipeOut,
    status_code=status.HTTP_201_CREATED,
)
async def criar_equipe(
    payload: EquipeIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_aprovador),
) -> EquipeOut:
    cli = (await db.execute(
        select(Cliente).where(Cliente.id == payload.cliente_id)
    )).scalar_one_or_none()
    if cli is None:
        raise ValidacaoError("Cliente não encontrado")

    eq = EquipeFlex(
        cliente_id=payload.cliente_id,
        nome=payload.nome.strip(),
        categoria=payload.categoria.strip(),
        valor_hora_centavos=payload.valor_hora_centavos,
        ativa=payload.ativa,
        observacoes=payload.observacoes,
    )
    db.add(eq)
    await db.flush()
    await db.refresh(eq, ["cliente", "membros"])
    log.info("equipe.criada", equipe_id=str(eq.id), cliente_id=str(cli.id))
    return _equipe_para_out(eq)


@router.get("/{equipe_id}", response_model=EquipeOut)
async def detalhar_equipe(
    equipe_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> EquipeOut:
    eq = await _carregar_equipe(db, equipe_id)
    return _equipe_para_out(eq)


@router.put("/{equipe_id}", response_model=EquipeOut)
async def atualizar_equipe(
    equipe_id: UUID,
    payload: EquipeIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_aprovador),
) -> EquipeOut:
    eq = await _carregar_equipe(db, equipe_id)
    eq.cliente_id = payload.cliente_id
    eq.nome = payload.nome.strip()
    eq.categoria = payload.categoria.strip()
    eq.valor_hora_centavos = payload.valor_hora_centavos
    eq.ativa = payload.ativa
    eq.observacoes = payload.observacoes
    await db.flush()
    await db.refresh(eq, ["cliente", "membros"])
    return _equipe_para_out(eq)


@router.delete("/{equipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deletar_equipe(
    equipe_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    eq = await _carregar_equipe(db, equipe_id)
    await db.delete(eq)
    await db.flush()


# ============================================================
# Membros
# ============================================================


@router.post(
    "/{equipe_id}/membros",
    response_model=MembroEquipeOut,
    status_code=status.HTTP_201_CREATED,
)
async def adicionar_membro(
    equipe_id: UUID,
    payload: MembroEquipeIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_aprovador),
) -> MembroEquipeOut:
    eq = await _carregar_equipe(db, equipe_id)

    # Bloqueia duplicidade pelo CPF dentro da mesma equipe
    if any(m.cpf == payload.cpf for m in eq.membros):
        raise ValidacaoError(
            f"Membro com CPF {payload.cpf} já está cadastrado nesta equipe"
        )

    membro = MembroEquipe(
        equipe_id=eq.id,
        nome=payload.nome.strip(),
        cpf=payload.cpf,
        crm_ou_registro=payload.crm_ou_registro,
        chave_pix=payload.chave_pix,
        banco_codigo=payload.banco_codigo,
        agencia=payload.agencia,
        conta=payload.conta,
        ativo=payload.ativo,
    )
    db.add(membro)
    await db.flush()
    await db.refresh(membro)
    return MembroEquipeOut.model_validate(membro)


@router.put(
    "/{equipe_id}/membros/{membro_id}",
    response_model=MembroEquipeOut,
)
async def atualizar_membro(
    equipe_id: UUID,
    membro_id: UUID,
    payload: MembroEquipeIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_aprovador),
) -> MembroEquipeOut:
    q = await db.execute(
        select(MembroEquipe).where(
            MembroEquipe.id == membro_id,
            MembroEquipe.equipe_id == equipe_id,
        )
    )
    membro = q.scalar_one_or_none()
    if membro is None:
        raise _nao_encontrado("Membro não encontrado nesta equipe")

    membro.nome = payload.nome.strip()
    membro.cpf = payload.cpf
    membro.crm_ou_registro = payload.crm_ou_registro
    membro.chave_pix = payload.chave_pix
    membro.banco_codigo = payload.banco_codigo
    membro.agencia = payload.agencia
    membro.conta = payload.conta
    membro.ativo = payload.ativo
    await db.flush()
    await db.refresh(membro)
    return MembroEquipeOut.model_validate(membro)


@router.delete(
    "/{equipe_id}/membros/{membro_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remover_membro(
    equipe_id: UUID,
    membro_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_aprovador),
) -> None:
    q = await db.execute(
        select(MembroEquipe).where(
            MembroEquipe.id == membro_id,
            MembroEquipe.equipe_id == equipe_id,
        )
    )
    membro = q.scalar_one_or_none()
    if membro is None:
        raise _nao_encontrado("Membro não encontrado nesta equipe")
    await db.delete(membro)
    await db.flush()


# ============================================================
# Fechamento mensal
# ============================================================


def _formatar_competencia_pt(competencia: str) -> str:
    """`2026-06` -> `Junho/2026`."""
    nomes = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    ]
    try:
        ano, mes = competencia.split("-")
        return f"{nomes[int(mes) - 1]}/{ano}"
    except (ValueError, IndexError):
        return competencia


def _gerar_xlsx_pagamentos_iguais(
    membros: list[MembroEquipe], valor_por_membro_centavos: int
) -> bytes:
    """Monta XLSX no formato que o LoteService espera (CPF/Nome/Banco/...)."""
    valor_reais = valor_por_membro_centavos / 100
    valor_str = f"{valor_reais:.2f}".replace(".", ",")

    rows: list[dict[str, str]] = []
    for m in membros:
        rows.append(
            {
                "CPF": m.cpf,
                "Nome": m.nome,
                "Banco": m.banco_codigo or "",
                "Agência": m.agencia or "",
                "Conta": m.conta or "",
                "Chave PIX": m.chave_pix or "",
                "Valor": valor_str,
            }
        )
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Equipe")
    return buf.getvalue()


@router.post("/fechamento", response_model=FechamentoOut)
async def fechar_mes_equipe(
    payload: FechamentoIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FechamentoOut:
    """Calcula (preview) ou confirma o fechamento mensal de uma equipe.

    Quando `confirmar=False`: só devolve os números calculados (sem persistir).
        Útil pra UI mostrar pro Sandro o que vai acontecer ANTES de criar o lote.

    Quando `confirmar=True`: persiste o fechamento, gera o lote de pagamento
        com 1 linha por membro ativo (todos com o mesmo valor), e marca o
        fechamento como aprovado pelo current_user.

    Coordenador pode visualizar (preview), mas só APROVADOR confirma.
    """
    eq = await _carregar_equipe(db, payload.equipe_id)

    if payload.confirmar and current_user.role == UserRole.COORDENADOR:
        raise PermissaoNegadaError(
            "Coordenador não pode confirmar fechamento. Encaminhe pro aprovador."
        )

    membros_ativos = [m for m in eq.membros if m.ativo]
    if not membros_ativos:
        raise ValidacaoError(
            "Equipe não tem membros ativos. Cadastre/reative pelo menos 1 antes de fechar."
        )

    # Cálculo do bruto
    valor_bruto = payload.horas_total * eq.valor_hora_centavos
    if valor_bruto <= 0:
        raise ValidacaoError("Valor bruto calculado é zero. Confira valor/hora e horas totais.")

    # Modo de cobrança do hospital → desconto MedPag
    contrato_q = await db.execute(
        select(ContratoHospital).where(
            ContratoHospital.cliente_id == eq.cliente_id,
            ContratoHospital.ativo.is_(True),
        )
    )
    contrato = contrato_q.scalar_one_or_none()
    pct_bp = _pegar_pct_medpag_bp(contrato)
    desconto = (valor_bruto * pct_bp) // 10000  # bp = parts per 10k
    valor_liquido = valor_bruto - desconto
    if valor_liquido <= 0:
        raise ValidacaoError(
            "Valor líquido após desconto MedPag é zero. Reveja o contrato."
        )

    qtd = len(membros_ativos)
    valor_por_membro = valor_liquido // qtd  # arredonda pra baixo

    # Verificar se já existe fechamento pra esse mês
    fech_q = await db.execute(
        select(FechamentoEquipe).where(
            FechamentoEquipe.equipe_id == eq.id,
            FechamentoEquipe.competencia == payload.competencia,
        )
    )
    existente = fech_q.scalar_one_or_none()
    if existente and not payload.confirmar:
        # Preview de um mês que já existe — só devolve o existente
        return FechamentoOut(
            id=existente.id,
            equipe_id=existente.equipe_id,
            competencia=existente.competencia,
            horas_total=existente.horas_total,
            valor_hora_centavos=existente.valor_hora_centavos,
            valor_bruto_centavos=existente.valor_bruto_centavos,
            desconto_medpag_centavos=existente.desconto_medpag_centavos,
            valor_liquido_centavos=existente.valor_liquido_centavos,
            qtd_membros=existente.qtd_membros,
            valor_por_membro_centavos=existente.valor_por_membro_centavos,
            origem=existente.origem,
            ficha_id=existente.ficha_id,
            lote_id=existente.lote_id,
            aprovado_at=existente.aprovado_at,
            observacoes=existente.observacoes,
            created_at=existente.created_at,
        )

    if existente and payload.confirmar:
        raise ValidacaoError(
            f"Já existe fechamento confirmado para {payload.competencia} "
            "nesta equipe. Apague o anterior antes de criar outro."
        )

    if not payload.confirmar:
        # Apenas preview — não persiste
        return FechamentoOut(
            id=None,
            equipe_id=eq.id,
            competencia=payload.competencia,
            horas_total=payload.horas_total,
            valor_hora_centavos=eq.valor_hora_centavos,
            valor_bruto_centavos=valor_bruto,
            desconto_medpag_centavos=desconto,
            valor_liquido_centavos=valor_liquido,
            qtd_membros=qtd,
            valor_por_membro_centavos=valor_por_membro,
            origem=payload.origem,
            ficha_id=payload.ficha_id,
            lote_id=None,
            aprovado_at=None,
            observacoes=payload.observacoes,
            created_at=None,
        )

    # ===== Confirmar — gera lote =====
    from app.services.lote import LoteService  # import local pra evitar ciclo

    xlsx_bytes = _gerar_xlsx_pagamentos_iguais(membros_ativos, valor_por_membro)
    nome_xlsx = f"equipe-{eq.nome.lower().replace(' ', '-')}-{payload.competencia}.xlsx"

    lote_service = LoteService(db)
    lote, _info = await lote_service.criar_a_partir_de_upload(
        conteudo=xlsx_bytes,
        nome_arquivo=nome_xlsx,
        cliente=eq.cliente,
        enviado_por=current_user,
    )
    lote.referencia = f"Equipe {eq.nome} • {_formatar_competencia_pt(payload.competencia)}"

    fech = FechamentoEquipe(
        equipe_id=eq.id,
        competencia=payload.competencia,
        horas_total=payload.horas_total,
        valor_hora_centavos=eq.valor_hora_centavos,
        valor_bruto_centavos=valor_bruto,
        desconto_medpag_centavos=desconto,
        valor_liquido_centavos=valor_liquido,
        qtd_membros=qtd,
        valor_por_membro_centavos=valor_por_membro,
        origem=payload.origem,
        ficha_id=payload.ficha_id,
        lote_id=lote.id,
        aprovado_por_id=current_user.id,
        aprovado_at=datetime.now(timezone.utc),
        observacoes=payload.observacoes,
    )
    db.add(fech)
    await db.flush()
    await db.refresh(fech)

    log.info(
        "equipe.fechamento_confirmado",
        equipe_id=str(eq.id),
        competencia=payload.competencia,
        horas=payload.horas_total,
        bruto=valor_bruto,
        desconto=desconto,
        liquido=valor_liquido,
        qtd_membros=qtd,
        valor_por_membro=valor_por_membro,
        lote_id=str(lote.id),
    )

    return FechamentoOut.model_validate(fech)


@router.get("/{equipe_id}/fechamentos", response_model=list[FechamentoOut])
async def listar_fechamentos(
    equipe_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[FechamentoOut]:
    res = await db.execute(
        select(FechamentoEquipe)
        .where(FechamentoEquipe.equipe_id == equipe_id)
        .order_by(FechamentoEquipe.competencia.desc())
    )
    return [FechamentoOut.model_validate(f) for f in res.scalars().all()]
