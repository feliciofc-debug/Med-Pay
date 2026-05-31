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
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_db, require_admin, require_execucao_pagamento
from app.core.exceptions import (
    LoteNaoEncontradoError,
    UsuarioJaExisteError,
    UsuarioNaoEncontradoError,
    ValidacaoError,
)
from app.core.security import hash_password
from app.models.cliente import Cliente
from app.models.empresa_config import EmpresaConfig, TipoInscricao
from app.models.lote import Lote, StatusLote
from app.models.pagamento import Pagamento, StatusPagamento
from app.models.user import User, UserRole
from app.schemas.admin import (
    AtualizarUsuarioRequest,
    CriarUsuarioRequest,
    DevolucaoBanco,
    DevolucoesPorMotivo,
    EmpresaPagadoraOut,
    EmpresaPagadoraRequest,
    ErrosPorHospital,
    ErrosPorOperador,
    ErrosPorTipo,
    RelatorioDevolucoesResponse,
    RelatorioErrosResponse,
    ResetSenhaRequest,
    UserAdminOut,
)
from app.services.cnab_parser import CODIGOS_OCORRENCIA
from app.services.importacao import LinhaPlanilha, importar_planilha
from app.services.processamento import processar_lote

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
) -> UserAdminOut:
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
        cliente_id=payload.cliente_id,
        beneficiario_id=payload.beneficiario_id,
    )
    db.add(novo)
    await db.flush()
    # Refresh pra carregar server_default (created_at, updated_at) antes
    # da sessão fechar — evita DetachedInstanceError na serialização.
    await db.refresh(novo)

    log.info(
        "admin.user_criado",
        criado_por=admin.email,
        novo_usuario=novo.email,
        role=novo.role.value,
    )
    return UserAdminOut.model_validate(novo)


@router.patch("/users/{user_id}", response_model=UserAdminOut)
async def atualizar_usuario(
    user_id: UUID,
    payload: AtualizarUsuarioRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserAdminOut:
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
    if payload.beneficiario_id is not None:
        # Aceita string vazia (UUID nulo nao chega aqui) — pra desvincular
        # usa um endpoint dedicado se necessario.
        user.beneficiario_id = payload.beneficiario_id

    await db.flush()
    # Refresh garante que `updated_at` (com onupdate=func.now()) seja
    # lido do banco antes da sessão fechar. Sem isso, o lazy reload
    # explode com DetachedInstanceError quando FastAPI serializa.
    await db.refresh(user)

    log.info(
        "admin.user_atualizado",
        editado_por=admin.email,
        user=user.email,
        nome=user.nome,
        role=user.role.value,
        ativo=user.ativo,
    )
    return UserAdminOut.model_validate(user)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def deletar_usuario(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Response:
    """Remove um usuário definitivamente.

    Bloqueado quando:
      - O ADMIN tenta apagar a si mesmo.
      - O usuário tem histórico (lotes enviados/aprovados): nesse caso
        a única opção segura é **desativar** (preservar trilha de
        auditoria). Operadores antigos sempre devem ser desativados,
        nunca apagados, pra manter rastreabilidade de quem subiu/aprovou
        cada lote.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise UsuarioNaoEncontradoError(f"Usuário {user_id} não encontrado")

    if user.id == admin.id:
        raise ValidacaoError(
            "Você não pode excluir a si mesmo. Peça pra outro ADMIN."
        )

    qtd_lotes_enviados = await db.scalar(
        select(func.count(Lote.id)).where(Lote.enviado_por_id == user.id)
    )
    qtd_lotes_aprovados = await db.scalar(
        select(func.count(Lote.id)).where(Lote.aprovado_por_id == user.id)
    )
    if (qtd_lotes_enviados or 0) > 0 or (qtd_lotes_aprovados or 0) > 0:
        raise ValidacaoError(
            f"Usuário tem histórico no sistema "
            f"({qtd_lotes_enviados or 0} lotes enviados, "
            f"{qtd_lotes_aprovados or 0} aprovados) — não pode ser apagado "
            f"sem perder a auditoria. Use 'Desativar' em vez de excluir."
        )

    email_apagado = user.email
    await db.delete(user)
    await db.flush()

    log.info(
        "admin.user_deletado",
        deletado_por=admin.email,
        user_apagado=email_apagado,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============================================================
# Reprocessamento de lote (recurso operacional pra ADMIN)
# ============================================================


@router.delete(
    "/lotes/{lote_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def deletar_lote(
    lote_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Response:
    """Deleta um lote (e todos os pagamentos por cascade).

    Uso recomendado:
    - Lote em RECEBIDO sem arquivo em disco (reset do container)
    - Lote de teste que ficou bagunçado
    - Não use em lote APROVADO/ENVIADO_BANCO sem entender o impacto.

    REGRA: hash_conteudo é único, então deletar libera o hash pra
    upload da mesma planilha de novo (recomendado pra recuperar de
    falhas de processamento).
    """
    from sqlalchemy import delete

    result = await db.execute(select(Lote).where(Lote.id == lote_id))
    lote = result.scalar_one_or_none()
    if lote is None:
        raise LoteNaoEncontradoError(f"Lote {lote_id} não encontrado")

    if lote.status in (
        StatusLote.APROVADO,
        StatusLote.ENVIADO_BANCO,
        StatusLote.CONCILIADO,
    ):
        raise ValidacaoError(
            f"Lote em status {lote.status.value} não pode ser deletado "
            f"(já entrou no ciclo de pagamento). Cancele primeiro."
        )

    # Cascade delete: SQLAlchemy apaga os pagamentos junto
    await db.delete(lote)
    await db.flush()

    log.warning(
        "admin.lote_deletado",
        admin=admin.email,
        lote_id=str(lote_id),
        cliente_id=str(lote.cliente_id),
        status_antes=lote.status.value,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/lotes/{lote_id}/reprocessar")
async def reprocessar_lote(
    lote_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, object]:
    """Reprocessa um lote rodando o validador atual de novo.

    Estratégia:
    1. Se tiver o arquivo original em disco → reimporta da planilha.
    2. Senão → reconstrói as linhas a partir dos pagamentos já no banco
       (descriptografa CPF/agência/conta). Útil quando o container do
       Render foi reiniciado e o filesystem efêmero perdeu o arquivo.

    Cenários típicos:
    - Worker Celery indisponível no momento do upload.
    - Bug no validador foi corrigido e quer rodar de novo.
    - Lote em ERRO que pode ser recuperado.
    - Regras de banco mudaram (novos bancos suportados).

    Bloqueia apenas lotes que já entraram no ciclo de pagamento real.
    Idempotente: pagamentos antigos do lote são apagados antes.
    """
    from pathlib import Path

    from sqlalchemy import delete

    from app.core.crypto import decrypt

    result = await db.execute(select(Lote).where(Lote.id == lote_id))
    lote = result.scalar_one_or_none()
    if lote is None:
        raise LoteNaoEncontradoError(f"Lote {lote_id} não encontrado")

    if lote.status in (
        StatusLote.APROVADO,
        StatusLote.ENVIADO_BANCO,
        StatusLote.CONCILIADO,
    ):
        raise ValidacaoError(
            f"Lote em status {lote.status.value} não pode ser reprocessado "
            f"(já entrou no ciclo de pagamento)."
        )

    linhas: list[LinhaPlanilha] = []
    origem_reproc = "desconhecida"

    caminho = (
        Path(lote.caminho_arquivo_original) if lote.caminho_arquivo_original else None
    )
    if caminho is not None and caminho.exists():
        conteudo = caminho.read_bytes()
        importacao = importar_planilha(conteudo, lote.nome_arquivo)
        linhas = importacao.linhas
        origem_reproc = "arquivo"
    else:
        # Reconstrói a partir dos pagamentos no banco (descriptografando)
        result_pgs = await db.execute(
            select(Pagamento)
            .where(Pagamento.lote_id == lote_id)
            .order_by(Pagamento.linha_planilha.asc())
        )
        pagamentos_antigos = list(result_pgs.scalars().all())
        if not pagamentos_antigos:
            raise ValidacaoError(
                "Lote sem arquivo original e sem pagamentos no banco. "
                "Não dá pra reprocessar — faça upload de novo."
            )
        for p in pagamentos_antigos:
            try:
                cpf_raw = decrypt(p.cpf_encrypted) if p.cpf_encrypted else None
            except Exception:
                cpf_raw = p.cpf_original or p.cpf_mascarado
            try:
                agencia_raw = (
                    decrypt(p.agencia_encrypted) if p.agencia_encrypted else None
                )
            except Exception:
                agencia_raw = None
            try:
                conta_raw = decrypt(p.conta_encrypted) if p.conta_encrypted else None
            except Exception:
                conta_raw = None
            linhas.append(
                LinhaPlanilha(
                    numero_linha=p.linha_planilha,
                    cpf_raw=cpf_raw,
                    nome_raw=p.nome,
                    banco_raw=p.banco_codigo,
                    agencia_raw=agencia_raw,
                    conta_raw=conta_raw,
                    valor_raw=p.valor_centavos / 100,
                )
            )
        origem_reproc = "banco"

    # Limpa pagamentos antigos pra evitar duplicação
    await db.execute(delete(Pagamento).where(Pagamento.lote_id == lote_id))
    lote.status = StatusLote.RECEBIDO
    lote.mensagem_erro = None
    lote.total_validos = 0
    lote.total_corrigiveis = 0
    lote.total_bloqueados = 0
    await db.flush()

    resultado = await processar_lote(db, lote, linhas)
    await db.flush()

    log.info(
        "admin.lote_reprocessado",
        admin=admin.email,
        lote_id=str(lote_id),
        origem=origem_reproc,
        total=resultado.total,
        validos=resultado.validos,
        corrigiveis=resultado.corrigiveis,
        bloqueados=resultado.bloqueados,
    )

    return {
        "success": True,
        "lote_id": str(lote_id),
        "status": lote.status.value,
        "origem": origem_reproc,
        "total": resultado.total,
        "validos": resultado.validos,
        "corrigiveis": resultado.corrigiveis,
        "bloqueados": resultado.bloqueados,
    }


@router.post("/users/{user_id}/reset-senha", response_model=UserAdminOut)
async def reset_senha_usuario(
    user_id: UUID,
    payload: ResetSenhaRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserAdminOut:
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
    await db.refresh(user)  # Garante updated_at fresh antes de serializar

    log.info(
        "admin.senha_resetada",
        resetado_por=admin.email,
        user=user.email,
    )
    return UserAdminOut.model_validate(user)


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


# ============================================================
# Empresa Pagadora — dados que vão no Header CNAB 240
# ============================================================
#
# Singleton: existe no máximo uma empresa pagadora ativa por instalação.
# É o equivalente à aba INICIO do template Excel do Thiago: razão social,
# CNPJ, conta Unicred (Ag 1214-7 / CC 21390-0), endereço e sequencial.
#
# GET retorna 404 se ainda não foi configurada (estado inicial pós-deploy).
# PUT é idempotente: se já existir, atualiza; senão, cria. Sempre só um
# registro ativo — quando muda, o anterior vira inativo (auditável).


def _so_digitos(valor: str) -> str:
    return "".join(c for c in valor if c.isdigit())


def _scope_empresa_por_tenant(query, tenant_id: UUID | None):
    """Filtra EmpresaConfig pelo tenant do usuário.

    - MedPag interno (cliente_id None) → conta legada/global (cliente_id NULL),
      preservando a operação Auris que já roda hoje.
    - Empresa de repasse (ex.: Atom) → a conta do próprio tenant.

    É o que isola a empresa pagadora de cada operação: a Atom configura a
    conta dela sem mexer (nem enxergar) a da Auris.
    """
    if tenant_id is None:
        return query.where(EmpresaConfig.cliente_id.is_(None))
    return query.where(EmpresaConfig.cliente_id == tenant_id)


@router.get("/empresa-pagadora", response_model=EmpresaPagadoraOut)
async def obter_empresa_pagadora(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_execucao_pagamento),
) -> EmpresaConfig:
    """Retorna a empresa pagadora ativa DO TENANT do usuário.

    Se ainda não foi cadastrada, retorna 404 — o frontend deve mostrar
    a tela de cadastro vazia nesse caso.
    """
    query = _scope_empresa_por_tenant(
        select(EmpresaConfig).where(EmpresaConfig.ativo.is_(True)),
        user.cliente_id,
    )
    result = await db.execute(query.limit(1))
    empresa = result.scalar_one_or_none()
    if empresa is None:
        raise LoteNaoEncontradoError(
            "Empresa pagadora ainda não cadastrada. "
            "Use PUT /api/admin/empresa-pagadora para criar."
        )
    return empresa


@router.put("/empresa-pagadora", response_model=EmpresaPagadoraOut)
async def salvar_empresa_pagadora(
    payload: EmpresaPagadoraRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_execucao_pagamento),
) -> EmpresaConfig:
    """Cria ou atualiza a empresa pagadora ativa (idempotente).

    Regra de negócio:
    - Limpa caracteres não-numéricos do CNPJ/CPF e CEP antes de gravar
    - Conta é criptografada com Fernet (dado bancário sensível)
    - Conta mascarada é gerada automaticamente pra exibição em telas
    - Se já existir registro ativo, atualiza os campos; senão cria novo

    O `proximo_numero_sequencial` é preservado se já existia (não dá pra
    pular sequencial pra trás — banco vai recusar arquivo CNAB).
    """
    from app.core.crypto import encrypt, mask_conta

    cnpj_limpo = _so_digitos(payload.cnpj_cpf)
    if payload.tipo_inscricao == TipoInscricao.CNPJ and len(cnpj_limpo) != 14:
        raise ValidacaoError(
            f"CNPJ inválido: esperado 14 dígitos, recebido {len(cnpj_limpo)}"
        )
    if payload.tipo_inscricao == TipoInscricao.CPF and len(cnpj_limpo) != 11:
        raise ValidacaoError(
            f"CPF inválido: esperado 11 dígitos, recebido {len(cnpj_limpo)}"
        )

    cep_limpo = _so_digitos(payload.endereco_cep)
    if len(cep_limpo) != 8:
        raise ValidacaoError(
            f"CEP inválido: esperado 8 dígitos, recebido {len(cep_limpo)}"
        )

    conta_limpa = "".join(c for c in payload.conta.upper() if c.isdigit() or c == "X")
    if not conta_limpa:
        raise ValidacaoError("Conta não pode ser vazia")

    # Busca registro ativo existente DO TENANT (se houver)
    result = await db.execute(
        _scope_empresa_por_tenant(
            select(EmpresaConfig).where(EmpresaConfig.ativo.is_(True)),
            admin.cliente_id,
        ).limit(1)
    )
    empresa = result.scalar_one_or_none()

    conta_encrypted = encrypt(conta_limpa)
    conta_mascarada = mask_conta(conta_limpa)

    if empresa is None:
        empresa = EmpresaConfig(
            cliente_id=admin.cliente_id,
            razao_social=payload.razao_social.strip(),
            nome_fantasia=(payload.nome_fantasia or None),
            tipo_inscricao=payload.tipo_inscricao,
            cnpj_cpf=cnpj_limpo,
            banco_emissor=payload.banco_emissor,
            banco_codigo=payload.banco_codigo,
            agencia=payload.agencia,
            agencia_dv=payload.agencia_dv,
            conta_encrypted=conta_encrypted,
            conta_dv=payload.conta_dv,
            conta_mascarada=conta_mascarada,
            codigo_convenio=payload.codigo_convenio,
            endereco_logradouro=payload.endereco_logradouro,
            endereco_numero=payload.endereco_numero,
            endereco_complemento=(payload.endereco_complemento or None),
            endereco_cidade=payload.endereco_cidade,
            endereco_cep=cep_limpo,
            endereco_uf=payload.endereco_uf.upper(),
            proximo_numero_sequencial=payload.proximo_numero_sequencial,
            ativo=True,
        )
        db.add(empresa)
        acao = "criada"
    else:
        empresa.razao_social = payload.razao_social.strip()
        empresa.nome_fantasia = payload.nome_fantasia or None
        empresa.tipo_inscricao = payload.tipo_inscricao
        empresa.cnpj_cpf = cnpj_limpo
        empresa.banco_emissor = payload.banco_emissor
        empresa.banco_codigo = payload.banco_codigo
        empresa.agencia = payload.agencia
        empresa.agencia_dv = payload.agencia_dv
        empresa.conta_encrypted = conta_encrypted
        empresa.conta_dv = payload.conta_dv
        empresa.conta_mascarada = conta_mascarada
        empresa.codigo_convenio = payload.codigo_convenio
        empresa.endereco_logradouro = payload.endereco_logradouro
        empresa.endereco_numero = payload.endereco_numero
        empresa.endereco_complemento = payload.endereco_complemento or None
        empresa.endereco_cidade = payload.endereco_cidade
        empresa.endereco_cep = cep_limpo
        empresa.endereco_uf = payload.endereco_uf.upper()
        # Sequencial: só aceita se for >= ao atual (não regredir)
        if payload.proximo_numero_sequencial >= empresa.proximo_numero_sequencial:
            empresa.proximo_numero_sequencial = payload.proximo_numero_sequencial
        acao = "atualizada"

    try:
        await db.flush()
        # Recarrega tudo do banco pra garantir que os atributos populados
        # via server_default (created_at/updated_at) estejam disponíveis
        # quando o FastAPI serializar a resposta (response_model). Sem isso
        # o SQLAlchemy pode tentar lazy-load num atributo expirado depois
        # da session fechar, gerando DetachedInstanceError.
        await db.refresh(empresa)
    except Exception as exc:
        log.exception(
            "admin.empresa_pagadora_save_error",
            admin=admin.email,
            erro=str(exc),
            tipo_erro=type(exc).__name__,
        )
        raise ValidacaoError(
            f"Erro ao salvar empresa pagadora: {type(exc).__name__}: {exc}"
        ) from exc

    log.warning(
        "admin.empresa_pagadora_salva",
        admin=admin.email,
        acao=acao,
        razao_social=empresa.razao_social,
        cnpj_cpf=empresa.cnpj_cpf,
        banco=empresa.banco_codigo,
        agencia=empresa.agencia,
        conta_mascarada=empresa.conta_mascarada,
    )

    return empresa
