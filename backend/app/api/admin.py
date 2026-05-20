"""Rotas administrativas — gestão de usuários e relatórios estratégicos.

Tudo aqui é protegido por `require_admin`. Não tem como cair aqui sem
ser ADMIN, porque é a área onde o Thiago e a diretoria gerenciam o time
operacional e medem a saúde da operação.

A regra de ouro: **operador NUNCA acessa estes endpoints**. Mesmo que
ele descubra a URL, o middleware bloqueia.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_db, require_admin
from app.core.exceptions import (
    UsuarioJaExisteError,
    UsuarioNaoEncontradoError,
    ValidacaoError,
)
from app.core.security import hash_password
from app.models.cliente import Cliente
from app.models.lote import Lote
from app.models.pagamento import Pagamento, StatusPagamento
from app.models.user import User, UserRole
from app.schemas.admin import (
    AtualizarUsuarioRequest,
    CriarUsuarioRequest,
    DevolucaoBanco,
    DevolucoesPorMotivo,
    ErrosPorHospital,
    ErrosPorOperador,
    ErrosPorTipo,
    RelatorioDevolucoesResponse,
    RelatorioErrosResponse,
    ResetSenhaRequest,
    UserAdminOut,
)
from app.services.cnab_parser import CODIGOS_OCORRENCIA

log = structlog.get_logger()

router = APIRouter()


# ============================================================
# CRUD de usuários (operadores, aprovadores, admins)
# ============================================================


@router.get("/users", response_model=list[UserAdminOut])
async def listar_usuarios(
    role: UserRole | None = Query(default=None, description="Filtra por papel"),
    ativo: bool | None = Query(default=None, description="Só ativos ou só inativos"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[User]:
    """Lista todos os usuários do sistema.

    Disponível só pra ADMIN. Usa filtros opcionais para a UI de gestão
    do time operacional (ex: ver só operadores ativos).
    """
    query = select(User).order_by(User.nome.asc())
    if role is not None:
        query = query.where(User.role == role)
    if ativo is not None:
        query = query.where(User.ativo.is_(ativo))

    result = await db.execute(query)
    return list(result.scalars().all())


@router.post(
    "/users",
    response_model=UserAdminOut,
    status_code=status.HTTP_201_CREATED,
)
async def criar_usuario(
    payload: CriarUsuarioRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> User:
    """Cria operador, aprovador ou outro admin.

    O Thiago usa esse endpoint quando contrata gente nova: cria um
    operador, manda o login por whatsapp/email, e o cara já pode subir
    planilha. Após o primeiro login a senha pode ser trocada via reset.
    """
    email_normalizado = payload.email.lower().strip()

    existing = await db.execute(
        select(User).where(User.email == email_normalizado)
    )
    if existing.scalar_one_or_none() is not None:
        raise UsuarioJaExisteError(
            f"Já existe usuário com o e-mail {email_normalizado}"
        )

    novo = User(
        email=email_normalizado,
        nome=payload.nome.strip(),
        hashed_password=hash_password(payload.senha),
        role=payload.role,
        ativo=True,
    )
    db.add(novo)
    await db.flush()

    log.info(
        "admin.user_criado",
        criado_por=admin.email,
        novo_usuario=novo.email,
        role=novo.role.value,
    )
    return novo


@router.patch("/users/{user_id}", response_model=UserAdminOut)
async def atualizar_usuario(
    user_id: UUID,
    payload: AtualizarUsuarioRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> User:
    """Edita parcialmente um usuário (nome, role, ativo)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise UsuarioNaoEncontradoError(f"Usuário {user_id} não encontrado")

    if user.id == admin.id and payload.ativo is False:
        raise ValidacaoError(
            "Você não pode desativar a si mesmo. Peça pra outro ADMIN."
        )
    if user.id == admin.id and payload.role is not None and payload.role != UserRole.ADMIN:
        raise ValidacaoError(
            "Você não pode rebaixar a si mesmo de ADMIN. Peça pra outro ADMIN."
        )

    if payload.nome is not None:
        user.nome = payload.nome.strip()
    if payload.role is not None:
        user.role = payload.role
    if payload.ativo is not None:
        user.ativo = payload.ativo

    await db.flush()
    log.info(
        "admin.user_atualizado",
        editado_por=admin.email,
        user=user.email,
        nome=user.nome,
        role=user.role.value,
        ativo=user.ativo,
    )
    return user


@router.post("/users/{user_id}/reset-senha", response_model=UserAdminOut)
async def reset_senha_usuario(
    user_id: UUID,
    payload: ResetSenhaRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> User:
    """Reset de senha imposto pelo ADMIN.

    Cenário típico: operador esqueceu senha → liga pra TI → ADMIN reseta
    e passa a nova senha por canal interno. NÃO existe fluxo de auto-reset
    por email (decisão consciente: ambiente fechado, time pequeno).
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise UsuarioNaoEncontradoError(f"Usuário {user_id} não encontrado")

    user.hashed_password = hash_password(payload.nova_senha)
    await db.flush()

    log.info(
        "admin.senha_resetada",
        resetado_por=admin.email,
        user=user.email,
    )
    return user


# ============================================================
# Relatório de erros — feature crítica de governança
# ============================================================


def _calcula_taxa_erro(bloqueados: int, corrigiveis: int, total: int) -> float:
    """Retorna percentual com 2 casas. Evita divisão por zero."""
    if total <= 0:
        return 0.0
    return round(((bloqueados + corrigiveis) / total) * 100, 2)


@router.get("/relatorio-erros", response_model=RelatorioErrosResponse)
async def relatorio_erros(
    dias: int = Query(default=30, ge=1, le=365, description="Janela em dias"),
    cliente_id: UUID | None = Query(default=None),
    operador_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> RelatorioErrosResponse:
    """Relatório agregado de erros de planilha.

    Esse é o relatório que o Thiago apresenta pra diretoria. Mostra:

    - **Prejuízo evitado**: soma de pagamentos que seriam debitados errado
      e foram bloqueados pelo MedPag antes de virarem CNAB.
    - Ranking de operadores que mais erram (base para treinamento).
    - Tipos de erro mais comuns (CPF inválido, valor anômalo, conta errada).
    - Ranking de hospitais que mandam planilha mais suja (negociar SLA).

    A regra: **nada aqui é punitivo, é só visibilidade.** Quem erra,
    erra; o relatório só dá o número.
    """
    agora = datetime.now(UTC)
    inicio = agora - timedelta(days=dias)

    filtros_lote = [Lote.created_at >= inicio]
    if cliente_id is not None:
        filtros_lote.append(Lote.cliente_id == cliente_id)
    if operador_id is not None:
        filtros_lote.append(Lote.enviado_por_id == operador_id)

    # ============================================================
    # KPIs globais (uma query agregada)
    # ============================================================
    kpi_query = select(
        func.count(Lote.id).label("total_lotes"),
        func.coalesce(func.sum(Lote.total_pagamentos), 0).label("total_pagamentos"),
        func.coalesce(func.sum(Lote.total_bloqueados), 0).label("total_bloqueados"),
        func.coalesce(func.sum(Lote.total_corrigiveis), 0).label("total_corrigiveis"),
        func.coalesce(func.sum(Lote.valor_total_centavos), 0).label("valor_total"),
    ).where(and_(*filtros_lote))
    kpi = (await db.execute(kpi_query)).one()

    # Valor BLOQUEADO precisa olhar Pagamento (não Lote) — somar valores
    # de pagamentos com status=BLOQUEADO. Esse é o "prejuízo evitado".
    bloqueado_query = (
        select(func.coalesce(func.sum(Pagamento.valor_centavos), 0))
        .join(Lote, Lote.id == Pagamento.lote_id)
        .where(
            and_(
                *filtros_lote,
                Pagamento.status == StatusPagamento.BLOQUEADO,
            )
        )
    )
    valor_bloqueado = int((await db.execute(bloqueado_query)).scalar_one() or 0)

    # ============================================================
    # Por operador (quem subiu o lote)
    # ============================================================
    op_query = (
        select(
            User.id.label("uid"),
            User.nome.label("nome"),
            User.email.label("email"),
            func.count(Lote.id).label("total_lotes"),
            func.coalesce(func.sum(Lote.total_pagamentos), 0).label("total_pag"),
            func.coalesce(func.sum(Lote.total_bloqueados), 0).label("total_blq"),
            func.coalesce(func.sum(Lote.total_corrigiveis), 0).label("total_corr"),
        )
        .select_from(Lote)
        .outerjoin(User, User.id == Lote.enviado_por_id)
        .where(and_(*filtros_lote))
        .group_by(User.id, User.nome, User.email)
        .order_by(func.sum(Lote.total_bloqueados).desc().nullslast())
    )
    op_rows = (await db.execute(op_query)).all()

    # Buscar valor bloqueado por operador (separado pra não complicar a query principal)
    op_valor_blq_query = (
        select(
            Lote.enviado_por_id.label("uid"),
            func.coalesce(func.sum(Pagamento.valor_centavos), 0).label("valor_blq"),
        )
        .select_from(Pagamento)
        .join(Lote, Lote.id == Pagamento.lote_id)
        .where(
            and_(
                *filtros_lote,
                Pagamento.status == StatusPagamento.BLOQUEADO,
            )
        )
        .group_by(Lote.enviado_por_id)
    )
    op_valor_blq_map: dict[UUID | None, int] = {
        row.uid: int(row.valor_blq) for row in (await db.execute(op_valor_blq_query)).all()
    }

    por_operador: list[ErrosPorOperador] = []
    for row in op_rows:
        total_pag = int(row.total_pag or 0)
        total_blq = int(row.total_blq or 0)
        total_corr = int(row.total_corr or 0)
        por_operador.append(
            ErrosPorOperador(
                operador_id=row.uid,
                operador_nome=row.nome or "(sem operador associado)",
                operador_email=row.email,
                total_lotes=int(row.total_lotes or 0),
                total_pagamentos=total_pag,
                total_bloqueados=total_blq,
                total_corrigiveis=total_corr,
                taxa_erro_pct=_calcula_taxa_erro(total_blq, total_corr, total_pag),
                valor_bloqueado_centavos=op_valor_blq_map.get(row.uid, 0),
            )
        )

    # ============================================================
    # Por tipo de erro — usa o campo Pagamento.codigos_erro (CSV)
    # ============================================================
    erros_query = (
        select(
            Pagamento.codigos_erro,
            Pagamento.valor_centavos,
        )
        .join(Lote, Lote.id == Pagamento.lote_id)
        .where(
            and_(
                *filtros_lote,
                Pagamento.codigos_erro.isnot(None),
            )
        )
    )
    erros_rows = (await db.execute(erros_query)).all()

    tipos_dict: dict[str, dict[str, int]] = {}
    for row in erros_rows:
        codigos = (row.codigos_erro or "").split(",")
        for cod in codigos:
            cod_limpo = cod.strip().upper()
            if not cod_limpo:
                continue
            entry = tipos_dict.setdefault(cod_limpo, {"qtd": 0, "valor": 0})
            entry["qtd"] += 1
            entry["valor"] += int(row.valor_centavos or 0)

    # Descrições amigáveis dos códigos mais comuns
    descricoes_erro = {
        "CPF_INVALIDO": "CPF inválido (dígito verificador)",
        "CPF_CORRIGIVEL": "CPF corrigível (sugestão automática)",
        "CPF_VAZIO": "CPF não preenchido",
        "BANCO_INVALIDO": "Código de banco desconhecido",
        "BANCO_VAZIO": "Banco não informado",
        "CONTA_INVALIDA": "Número de conta inválido",
        "CONTA_VAZIA": "Conta não informada",
        "AGENCIA_INVALIDA": "Agência inválida",
        "VALOR_INVALIDO": "Valor não numérico ou negativo",
        "VALOR_SUSPEITO": "Valor fora do padrão histórico",
        "VALOR_ZERO": "Valor zerado",
        "NOME_VAZIO": "Nome do beneficiário não informado",
        "DUPLICIDADE": "Pagamento duplicado no lote",
        "DUPLICIDADE_HISTORICA": "Mesmo CPF+valor pago recentemente",
    }
    por_tipo = sorted(
        [
            ErrosPorTipo(
                codigo=cod,
                descricao=descricoes_erro.get(cod, cod),
                quantidade=data["qtd"],
                valor_centavos=data["valor"],
            )
            for cod, data in tipos_dict.items()
        ],
        key=lambda x: x.quantidade,
        reverse=True,
    )

    # ============================================================
    # Por hospital (cliente)
    # ============================================================
    hosp_query = (
        select(
            Cliente.id.label("cid"),
            Cliente.nome.label("nome"),
            func.count(Lote.id).label("total_lotes"),
            func.coalesce(func.sum(Lote.total_pagamentos), 0).label("total_pag"),
            func.coalesce(func.sum(Lote.total_bloqueados), 0).label("total_blq"),
        )
        .select_from(Lote)
        .join(Cliente, Cliente.id == Lote.cliente_id)
        .where(and_(*filtros_lote))
        .group_by(Cliente.id, Cliente.nome)
        .order_by(func.sum(Lote.total_bloqueados).desc().nullslast())
    )
    hosp_rows = (await db.execute(hosp_query)).all()

    por_hospital: list[ErrosPorHospital] = []
    for row in hosp_rows:
        total_pag = int(row.total_pag or 0)
        total_blq = int(row.total_blq or 0)
        por_hospital.append(
            ErrosPorHospital(
                cliente_id=row.cid,
                cliente_nome=row.nome,
                total_lotes=int(row.total_lotes or 0),
                total_pagamentos=total_pag,
                total_bloqueados=total_blq,
                taxa_erro_pct=_calcula_taxa_erro(total_blq, 0, total_pag),
            )
        )

    return RelatorioErrosResponse(
        periodo_inicio=inicio,
        periodo_fim=agora,
        total_lotes_processados=int(kpi.total_lotes or 0),
        total_pagamentos=int(kpi.total_pagamentos or 0),
        total_bloqueados=int(kpi.total_bloqueados or 0),
        total_corrigiveis=int(kpi.total_corrigiveis or 0),
        valor_total_centavos=int(kpi.valor_total or 0),
        valor_bloqueado_centavos=valor_bloqueado,
        taxa_erro_pct=_calcula_taxa_erro(
            int(kpi.total_bloqueados or 0),
            int(kpi.total_corrigiveis or 0),
            int(kpi.total_pagamentos or 0),
        ),
        por_operador=por_operador,
        por_tipo_erro=por_tipo,
        por_hospital=por_hospital,
    )


# ============================================================
# Devoluções do banco — visibilidade de motivos
# ============================================================


@router.get("/devolucoes", response_model=RelatorioDevolucoesResponse)
async def relatorio_devolucoes(
    dias: int = Query(default=30, ge=1, le=365),
    cliente_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> RelatorioDevolucoesResponse:
    """Pagamentos que o banco devolveu — com motivo decodificado.

    Esse é o segundo relatório crítico: hoje o Thiago descreve que o
    banco devolve pagamento e ninguém sabe o motivo. Aqui a gente
    consolida tudo: pega o `retorno_codigo` que o parser CNAB extraiu,
    cruza com a tabela de códigos FEBRABAN/Unicred, e mostra o motivo
    em português.

    Quando o código vem de uma tabela que não temos mapeada
    (`motivo_conhecido=False`), aparece destacado pra equipe pesquisar
    e completar a tabela em `services/cnab_parser.CODIGOS_OCORRENCIA`.
    """
    agora = datetime.now(UTC)
    inicio = agora - timedelta(days=dias)

    filtros = [
        Pagamento.status == StatusPagamento.NAO_PAGO,
        Lote.created_at >= inicio,
    ]
    if cliente_id is not None:
        filtros.append(Lote.cliente_id == cliente_id)

    detalhe_query = (
        select(Pagamento, Lote, Cliente, User)
        .select_from(Pagamento)
        .join(Lote, Lote.id == Pagamento.lote_id)
        .join(Cliente, Cliente.id == Lote.cliente_id)
        .outerjoin(User, User.id == Lote.enviado_por_id)
        .where(and_(*filtros))
        .order_by(Pagamento.updated_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(detalhe_query)).all()

    devolucoes: list[DevolucaoBanco] = []
    for pag, lote, cliente, operador in rows:
        codigo = (pag.retorno_codigo or "").strip().upper()
        # Se a descrição já veio gravada (parser preencheu), usa ela.
        # Senão, tenta traduzir agora pela tabela atual.
        descricao = pag.retorno_descricao
        if not descricao and codigo:
            descricao = CODIGOS_OCORRENCIA.get(codigo)
        motivo_conhecido = bool(descricao) and not descricao.startswith("Código ")

        devolucoes.append(
            DevolucaoBanco(
                pagamento_id=pag.id,
                lote_id=lote.id,
                lote_nome=lote.nome_arquivo,
                cliente_nome=cliente.nome,
                linha_planilha=pag.linha_planilha,
                nome_beneficiario=pag.nome,
                cpf_mascarado=pag.cpf_mascarado,
                valor_centavos=pag.valor_centavos,
                retorno_codigo=codigo or None,
                retorno_descricao=descricao,
                motivo_conhecido=motivo_conhecido,
                pago_at=pag.pago_at,
                operador_nome=operador.nome if operador else None,
            )
        )

    # Agregação por motivo
    motivos_dict: dict[str, dict[str, object]] = {}
    for dev in devolucoes:
        chave = dev.retorno_codigo or "SEM_CODIGO"
        entry = motivos_dict.setdefault(
            chave,
            {
                "codigo": chave,
                "descricao": dev.retorno_descricao or "Sem código de retorno",
                "qtd": 0,
                "valor": 0,
            },
        )
        entry["qtd"] = int(entry["qtd"]) + 1
        entry["valor"] = int(entry["valor"]) + dev.valor_centavos

    por_motivo = sorted(
        [
            DevolucoesPorMotivo(
                codigo=str(e["codigo"]),
                descricao=str(e["descricao"]),
                quantidade=int(e["qtd"]),
                valor_centavos=int(e["valor"]),
            )
            for e in motivos_dict.values()
        ],
        key=lambda x: x.quantidade,
        reverse=True,
    )

    return RelatorioDevolucoesResponse(
        periodo_inicio=inicio,
        periodo_fim=agora,
        total_devolucoes=len(devolucoes),
        total_motivo_conhecido=sum(1 for d in devolucoes if d.motivo_conhecido),
        total_motivo_desconhecido=sum(1 for d in devolucoes if not d.motivo_conhecido),
        valor_total_devolvido_centavos=sum(d.valor_centavos for d in devolucoes),
        por_motivo=por_motivo,
        devolucoes=devolucoes,
    )
