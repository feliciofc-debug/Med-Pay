"""Tools que o Jarvis (LLM Groq) pode chamar.

Cada tool é uma função `async` Python que recebe `db: AsyncSession` +
parâmetros tipados. O dispatcher (`jarvis_agent.py`) traduz o JSON do
tool_call do LLM em chamada Python e devolve o resultado também em JSON.

REGRA DE OURO: tool nunca levanta exceção pro LLM. Se algo der errado,
devolve um dict com `{"erro": "..."}`. O LLM lê e responde ao usuário
em linguagem natural ("Não consegui buscar isso porque…").

Isolamento: tools NÃO podem ler request HTTP, cookie, header. Recebem
só o user_id de quem está conversando (vem do whitelist do WhatsApp).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
import sqlalchemy as sa
from sqlalchemy import String, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cliente import Cliente
from app.models.ficha_plantao import FichaPlantao, StatusFicha
from app.models.lote import Lote, StatusLote
from app.models.pagamento import Pagamento, StatusPagamento
from app.models.user import User, UserRole

log = structlog.get_logger()


# ============================================================
# Schema das tools (formato OpenAI tool calling)
# ============================================================
#
# A descrição precisa ser cristalina — é o que o LLM lê pra decidir
# QUANDO usar a tool. Quanto mais explícito o "use isto quando…",
# menos a IA chuta resposta.

TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "resumo_operacional_hoje",
            "description": (
                "Retorna o panorama operacional do dia atual: lotes recebidos, "
                "lotes aprovados hoje, valor total processado, lotes pendentes "
                "de revisão e fichas em processamento. Use SEMPRE que o usuário "
                "perguntar 'como tá o dia?', 'situação', 'panorama', 'bom dia', "
                "ou pedir um resumo geral."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_lotes_pendentes",
            "description": (
                "Lista lotes que estão AGUARDANDO_REVISAO — ou seja, "
                "esperando aprovação financeira pra gerar CNAB. Use quando o "
                "usuário perguntar 'o que falta aprovar?', 'pendentes', "
                "'fila de aprovação'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limite": {
                        "type": "integer",
                        "description": "Quantos lotes listar (default 10, máx 30)",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detalhar_lote",
            "description": (
                "Detalhe completo de um lote: cliente, status, total de "
                "pagamentos, valor, breakdown por status, top 3 erros. "
                "Use quando o usuário pedir 'detalhe do lote X', 'me fala do "
                "lote tal', ou logo antes de aprovar (pra confirmar totais)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lote_id_ou_prefixo": {
                        "type": "string",
                        "description": (
                            "ID completo (UUID) ou prefixo curto do lote "
                            "(ex: '7f3a' para casar com o início do UUID)."
                        ),
                    }
                },
                "required": ["lote_id_ou_prefixo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aprovar_lote",
            "description": (
                "APROVA um lote pendente, gerando o CNAB. Esta tool exige "
                "confirmação explícita: o usuário precisa ter dito EXPLICITAMENTE "
                "'confirmo', 'pode aprovar', 'sim aprovar lote X', com ID claro. "
                "Se não tem confirmação clara, NÃO chame essa tool — em vez disso "
                "responda mostrando o resumo via detalhar_lote e peça confirmação. "
                "Apenas usuários com flag pode_aprovar_pagamento conseguem usar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lote_id_ou_prefixo": {
                        "type": "string",
                        "description": "ID ou prefixo do lote a aprovar.",
                    }
                },
                "required": ["lote_id_ou_prefixo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kpis_mes_atual",
            "description": (
                "KPIs financeiros e operacionais do mês corrente: valor total "
                "processado, número de lotes, número de pagamentos, taxa de erro, "
                "valor devolvido pelo banco. Use quando o usuário perguntar "
                "'faturamento', 'volume do mês', 'KPIs', 'métricas', 'como tá o mês'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ranking_operadores",
            "description": (
                "Ranking dos operadores que mais subiram lotes (com taxa de "
                "erro de cada um). Use quando o usuário pedir 'ranking', "
                "'quem tá errando mais', 'quem tá produzindo'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "devolucoes_recentes",
            "description": (
                "Lista os pagamentos com retorno de 'NAO_PAGO' (devolvidos "
                "pelo banco) nos últimos N dias. Use pra perguntas tipo "
                "'devoluções', 'rejeições', 'o que voltou'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dias": {
                        "type": "integer",
                        "description": "Janela em dias (default 7, máx 30)",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fichas_pendentes",
            "description": (
                "Lista fichas de plantão (módulo OCR) aguardando revisão "
                "ou em erro. Use pra 'fichas pendentes', 'OCR', 'fichas com "
                "problema'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_cliente",
            "description": (
                "Busca um cliente (hospital/clínica) pelo nome parcial e "
                "retorna estatísticas: lotes do mês, valor processado, "
                "última atividade. Use quando o usuário citar um cliente "
                "pelo nome ('como tá o Auris?', 'situação do hospital X')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_parcial": {
                        "type": "string",
                        "description": "Trecho do nome do cliente",
                    }
                },
                "required": ["nome_parcial"],
            },
        },
    },
]


# ============================================================
# Helpers
# ============================================================


def _ini_dia() -> datetime:
    agora = datetime.now(UTC)
    return agora.replace(hour=0, minute=0, second=0, microsecond=0)


def _ini_mes() -> datetime:
    agora = datetime.now(UTC)
    return agora.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )


def _formatar_lote_curto(lote: Lote) -> dict[str, Any]:
    return {
        "id": str(lote.id),
        "id_curto": str(lote.id)[:8],
        "cliente": lote.cliente.nome if lote.cliente else "?",
        "referencia": lote.referencia or "—",
        "status": lote.status.value,
        "total_pagamentos": lote.total_pagamentos,
        "validos": lote.total_validos,
        "corrigiveis": lote.total_corrigiveis,
        "bloqueados": lote.total_bloqueados,
        "valor_total_reais": lote.valor_total_centavos / 100,
        "criado_em": lote.created_at.isoformat() if lote.created_at else None,
    }


async def _resolver_lote(
    db: AsyncSession, lote_id_ou_prefixo: str
) -> Lote | None:
    """Aceita UUID completo OU prefixo (primeiros chars do UUID)."""
    s = (lote_id_ou_prefixo or "").strip().lower()
    if not s:
        return None

    # Tenta UUID completo
    try:
        uid = UUID(s)
        result = await db.execute(
            select(Lote)
            .where(Lote.id == uid)
            .options(selectinload(Lote.cliente), selectinload(Lote.pagamentos))
        )
        return result.scalar_one_or_none()
    except ValueError:
        pass

    # Prefixo: cast id pra texto e busca por ilike
    result = await db.execute(
        select(Lote)
        .where(sa.cast(Lote.id, String).ilike(f"{s}%"))
        .options(selectinload(Lote.cliente), selectinload(Lote.pagamentos))
        .limit(2)
    )
    rows = list(result.scalars().all())
    if len(rows) == 1:
        return rows[0]
    return None


# ============================================================
# Tools (implementação)
# ============================================================


async def resumo_operacional_hoje(db: AsyncSession, _user: User) -> dict[str, Any]:
    inicio = _ini_dia()

    # Lotes recebidos hoje
    recebidos_q = await db.execute(
        select(func.count(Lote.id), func.coalesce(func.sum(Lote.valor_total_centavos), 0))
        .where(Lote.created_at >= inicio)
    )
    qtd_hoje, valor_hoje = recebidos_q.one()

    # Aprovados hoje
    aprovados_q = await db.execute(
        select(
            func.count(Lote.id),
            func.coalesce(func.sum(Lote.valor_total_centavos), 0),
        ).where(Lote.aprovado_at >= inicio)
    )
    qtd_aprov, valor_aprov = aprovados_q.one()

    # Pendentes (qualquer dia, status AGUARDANDO_REVISAO)
    pend_q = await db.execute(
        select(
            func.count(Lote.id),
            func.coalesce(func.sum(Lote.valor_total_centavos), 0),
        ).where(Lote.status == StatusLote.AGUARDANDO_REVISAO)
    )
    qtd_pend, valor_pend = pend_q.one()

    # Fichas em PROCESSANDO ou ERRO
    fichas_q = await db.execute(
        select(FichaPlantao.status, func.count(FichaPlantao.id))
        .where(
            FichaPlantao.status.in_(
                [StatusFicha.PROCESSANDO, StatusFicha.EXTRAIDA, StatusFicha.ERRO]
            )
        )
        .group_by(FichaPlantao.status)
    )
    fichas_por_status = {s.value: int(n) for s, n in fichas_q.all()}

    return {
        "dia": inicio.date().isoformat(),
        "lotes_recebidos_hoje": int(qtd_hoje),
        "valor_recebido_hoje_reais": float(valor_hoje) / 100,
        "lotes_aprovados_hoje": int(qtd_aprov),
        "valor_aprovado_hoje_reais": float(valor_aprov) / 100,
        "lotes_pendentes_aprovacao": int(qtd_pend),
        "valor_pendente_aprovacao_reais": float(valor_pend) / 100,
        "fichas_por_status": fichas_por_status,
    }


async def listar_lotes_pendentes(
    db: AsyncSession, _user: User, *, limite: int = 10
) -> dict[str, Any]:
    limite = max(1, min(int(limite or 10), 30))
    result = await db.execute(
        select(Lote)
        .where(Lote.status == StatusLote.AGUARDANDO_REVISAO)
        .options(selectinload(Lote.cliente))
        .order_by(Lote.created_at.asc())
        .limit(limite)
    )
    lotes = list(result.scalars().all())
    return {
        "total": len(lotes),
        "lotes": [_formatar_lote_curto(l) for l in lotes],
    }


async def detalhar_lote(
    db: AsyncSession, _user: User, *, lote_id_ou_prefixo: str
) -> dict[str, Any]:
    lote = await _resolver_lote(db, lote_id_ou_prefixo)
    if not lote:
        return {
            "erro": "lote_nao_encontrado",
            "mensagem": (
                f"Não encontrei lote com identificador '{lote_id_ou_prefixo}'. "
                "Use pelo menos os 6 primeiros caracteres do ID."
            ),
        }

    # Top 3 erros mais frequentes
    erros: dict[str, int] = {}
    for p in lote.pagamentos or []:
        if p.codigos_erro:
            for codigo in p.codigos_erro.split(","):
                codigo = codigo.strip()
                if codigo:
                    erros[codigo] = erros.get(codigo, 0) + 1
    top_erros = sorted(erros.items(), key=lambda kv: -kv[1])[:3]

    base = _formatar_lote_curto(lote)
    base.update(
        {
            "aprovado_em": (
                lote.aprovado_at.isoformat() if lote.aprovado_at else None
            ),
            "nome_arquivo": lote.nome_arquivo,
            "nome_arquivo_cnab": lote.nome_arquivo_cnab,
            "top_erros": [{"codigo": c, "qtd": q} for c, q in top_erros],
        }
    )
    return base


async def aprovar_lote(
    db: AsyncSession, user: User, *, lote_id_ou_prefixo: str
) -> dict[str, Any]:
    """Aprova lote pelo Jarvis. Importante:

    - Apenas user com `pode_aprovar_pagamento` no `WhatsAppUser` chega aqui
      (filtro feito no agente antes de invocar a tool).
    - User ainda precisa ter role ADMIN ou APROVADOR.
    - Após aprovação, a auditoria registra "aprovado via Jarvis WhatsApp".
    """
    from app.services.lote import LoteService

    if user.role not in (UserRole.ADMIN, UserRole.APROVADOR):
        return {
            "erro": "permissao",
            "mensagem": "Seu usuário não tem permissão pra aprovar lotes.",
        }

    lote = await _resolver_lote(db, lote_id_ou_prefixo)
    if not lote:
        return {
            "erro": "lote_nao_encontrado",
            "mensagem": (
                f"Não encontrei lote '{lote_id_ou_prefixo}'."
            ),
        }

    if lote.status != StatusLote.AGUARDANDO_REVISAO:
        return {
            "erro": "status_invalido",
            "mensagem": (
                f"Lote {str(lote.id)[:8]} está em {lote.status.value}, "
                "não pode ser aprovado."
            ),
        }

    aprovaveis = [
        p
        for p in lote.pagamentos
        if p.status in (StatusPagamento.VALIDO, StatusPagamento.CORRIGIVEL)
    ]
    soma = sum(p.valor_centavos for p in aprovaveis)
    qtd = len(aprovaveis)

    service = LoteService(db)
    try:
        resultado = await service.aprovar(
            lote.id,
            aprovador=user,
            observacoes="Aprovado via Jarvis (WhatsApp)",
            confirmacao_total_centavos=soma,
            confirmacao_qtd_pagamentos=qtd,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("jarvis.aprovar_falhou", lote_id=str(lote.id))
        return {
            "erro": "falha_aprovacao",
            "mensagem": str(exc),
        }

    return {
        "sucesso": True,
        "lote_id": str(lote.id)[:8],
        "qtd_pagamentos": resultado.quantidade_pagamentos,
        "valor_total_reais": resultado.valor_total_centavos / 100,
        "nome_arquivo_cnab": resultado.nome_arquivo,
        "mensagem": (
            f"Lote {str(lote.id)[:8]} aprovado. "
            f"CNAB '{resultado.nome_arquivo}' gerado com "
            f"{resultado.quantidade_pagamentos} pagamentos totalizando "
            f"R$ {resultado.valor_total_centavos / 100:,.2f}. "
            "Baixe pelo painel pra subir na Unicred."
        ),
    }


async def kpis_mes_atual(db: AsyncSession, _user: User) -> dict[str, Any]:
    inicio = _ini_mes()

    # Volume processado (lotes APROVADO/ENVIADO/CONCILIADO desde o início do mês)
    proc_q = await db.execute(
        select(
            func.count(Lote.id),
            func.coalesce(func.sum(Lote.valor_total_centavos), 0),
            func.coalesce(func.sum(Lote.total_pagamentos), 0),
        ).where(
            Lote.created_at >= inicio,
            Lote.status.in_(
                [
                    StatusLote.APROVADO,
                    StatusLote.ENVIADO_BANCO,
                    StatusLote.CONCILIADO,
                ]
            ),
        )
    )
    qtd_lotes, valor_total, qtd_pagamentos = proc_q.one()

    # Pagamentos NAO_PAGO no mês (devoluções)
    devo_q = await db.execute(
        select(
            func.count(Pagamento.id),
            func.coalesce(func.sum(Pagamento.valor_centavos), 0),
        )
        .join(Lote, Pagamento.lote_id == Lote.id)
        .where(
            Lote.created_at >= inicio,
            Pagamento.status == StatusPagamento.NAO_PAGO,
        )
    )
    qtd_devo, valor_devo = devo_q.one()

    # Erros (BLOQUEADO) no mês
    erros_q = await db.execute(
        select(func.count(Pagamento.id))
        .join(Lote, Pagamento.lote_id == Lote.id)
        .where(
            Lote.created_at >= inicio,
            Pagamento.status == StatusPagamento.BLOQUEADO,
        )
    )
    qtd_bloq = erros_q.scalar_one()

    total_pag = int(qtd_pagamentos)
    taxa_erro = (int(qtd_bloq) / total_pag * 100) if total_pag > 0 else 0.0

    return {
        "mes": inicio.strftime("%m/%Y"),
        "lotes_processados": int(qtd_lotes),
        "pagamentos_processados": total_pag,
        "valor_total_reais": float(valor_total) / 100,
        "devolucoes_qtd": int(qtd_devo),
        "valor_devolvido_reais": float(valor_devo) / 100,
        "pagamentos_bloqueados": int(qtd_bloq),
        "taxa_erro_pct": round(taxa_erro, 2),
    }


async def ranking_operadores(
    db: AsyncSession, _user: User
) -> dict[str, Any]:
    inicio = _ini_mes()
    result = await db.execute(
        select(
            User.id,
            User.nome,
            User.email,
            func.count(Lote.id).label("lotes"),
            func.coalesce(func.sum(Lote.total_pagamentos), 0).label("pgs"),
            func.coalesce(func.sum(Lote.total_bloqueados), 0).label("bloq"),
            func.coalesce(func.sum(Lote.valor_total_centavos), 0).label("valor"),
        )
        .join(Lote, Lote.enviado_por_id == User.id)
        .where(Lote.created_at >= inicio)
        .group_by(User.id, User.nome, User.email)
        .order_by(desc("lotes"))
        .limit(10)
    )
    operadores = []
    for row in result.all():
        pgs = int(row.pgs)
        bloq = int(row.bloq)
        operadores.append(
            {
                "user_id": str(row.id),
                "nome": row.nome,
                "email": row.email,
                "lotes": int(row.lotes),
                "pagamentos": pgs,
                "bloqueados": bloq,
                "taxa_erro_pct": (bloq / pgs * 100) if pgs else 0.0,
                "valor_total_reais": float(row.valor) / 100,
            }
        )
    return {"mes": inicio.strftime("%m/%Y"), "operadores": operadores}


async def devolucoes_recentes(
    db: AsyncSession, _user: User, *, dias: int = 7
) -> dict[str, Any]:
    dias = max(1, min(int(dias or 7), 30))
    inicio = datetime.now(UTC) - timedelta(days=dias)
    result = await db.execute(
        select(Pagamento, Lote.nome_arquivo, Cliente.nome)
        .join(Lote, Pagamento.lote_id == Lote.id)
        .join(Cliente, Lote.cliente_id == Cliente.id)
        .where(
            Pagamento.status == StatusPagamento.NAO_PAGO,
            Pagamento.updated_at >= inicio,
        )
        .order_by(desc(Pagamento.updated_at))
        .limit(20)
    )
    devolucoes = []
    valor_total = 0
    for pag, lote_nome, cliente_nome in result.all():
        devolucoes.append(
            {
                "lote": lote_nome,
                "cliente": cliente_nome,
                "beneficiario": pag.nome,
                "cpf": pag.cpf_mascarado,
                "valor_reais": pag.valor_centavos / 100,
                "motivo_codigo": pag.retorno_codigo,
                "motivo": pag.retorno_descricao,
            }
        )
        valor_total += pag.valor_centavos
    return {
        "dias": dias,
        "total": len(devolucoes),
        "valor_total_reais": valor_total / 100,
        "devolucoes": devolucoes,
    }


async def fichas_pendentes(db: AsyncSession, _user: User) -> dict[str, Any]:
    result = await db.execute(
        select(FichaPlantao)
        .where(
            FichaPlantao.status.in_(
                [
                    StatusFicha.RECEBIDA,
                    StatusFicha.PROCESSANDO,
                    StatusFicha.EXTRAIDA,
                    StatusFicha.ERRO,
                ]
            )
        )
        .options(selectinload(FichaPlantao.cliente))
        .order_by(FichaPlantao.created_at.desc())
        .limit(15)
    )
    fichas = []
    for ficha in result.scalars().all():
        fichas.append(
            {
                "id_curto": str(ficha.id)[:8],
                "arquivo": ficha.nome_arquivo,
                "cliente": ficha.cliente.nome if ficha.cliente else "?",
                "status": ficha.status.value,
                "linhas": ficha.total_linhas,
                "valor_reais": ficha.valor_total_centavos / 100,
                "erro": ficha.mensagem_erro,
                "criado_em": ficha.created_at.isoformat(),
            }
        )
    return {"total": len(fichas), "fichas": fichas}


async def buscar_cliente(
    db: AsyncSession, _user: User, *, nome_parcial: str
) -> dict[str, Any]:
    s = (nome_parcial or "").strip()
    if not s or len(s) < 2:
        return {"erro": "consulta_curta", "mensagem": "Nome muito curto"}

    result = await db.execute(
        select(Cliente)
        .where(Cliente.nome.ilike(f"%{s}%"), Cliente.ativo.is_(True))
        .limit(5)
    )
    clientes = list(result.scalars().all())

    if not clientes:
        return {
            "encontrados": 0,
            "mensagem": f"Nenhum cliente ativo com nome '{s}'",
        }

    inicio = _ini_mes()
    saida = []
    for cliente in clientes:
        stats_q = await db.execute(
            select(
                func.count(Lote.id),
                func.coalesce(func.sum(Lote.valor_total_centavos), 0),
                func.max(Lote.created_at),
            ).where(Lote.cliente_id == cliente.id, Lote.created_at >= inicio)
        )
        qtd_lotes, valor_mes, ultima = stats_q.one()
        saida.append(
            {
                "id": str(cliente.id),
                "nome": cliente.nome,
                "cnpj": cliente.cnpj,
                "lotes_no_mes": int(qtd_lotes),
                "valor_mes_reais": float(valor_mes) / 100,
                "ultima_atividade": ultima.isoformat() if ultima else None,
            }
        )
    return {"encontrados": len(saida), "clientes": saida}


# ============================================================
# Dispatcher
# ============================================================


_DISPATCH: dict[str, Any] = {
    "resumo_operacional_hoje": resumo_operacional_hoje,
    "listar_lotes_pendentes": listar_lotes_pendentes,
    "detalhar_lote": detalhar_lote,
    "aprovar_lote": aprovar_lote,
    "kpis_mes_atual": kpis_mes_atual,
    "ranking_operadores": ranking_operadores,
    "devolucoes_recentes": devolucoes_recentes,
    "fichas_pendentes": fichas_pendentes,
    "buscar_cliente": buscar_cliente,
}


# Tools que exigem `pode_aprovar_pagamento=True` no WhatsAppUser.
# Se o usuário não tiver a flag, o agente responde "Você não tem permissão"
# sem nem chamar.
TOOLS_RESTRITAS_APROVACAO: frozenset[str] = frozenset({"aprovar_lote"})


async def executar_tool(
    db: AsyncSession,
    user: User,
    *,
    nome: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Despacha o tool_call do LLM para a função Python correspondente.

    Sempre retorna dict serializável em JSON.
    """
    func_alvo = _DISPATCH.get(nome)
    if func_alvo is None:
        return {"erro": "tool_desconhecida", "mensagem": f"Tool '{nome}' não existe."}

    try:
        result = await func_alvo(db, user, **(args or {}))
        return result if isinstance(result, dict) else {"resultado": result}
    except TypeError as exc:
        return {"erro": "args_invalidos", "mensagem": f"Parâmetros inválidos: {exc}"}
    except Exception as exc:  # noqa: BLE001
        log.exception("jarvis.tool_falhou", tool=nome)
        return {
            "erro": "falha_tool",
            "mensagem": f"Erro ao executar {nome}: {type(exc).__name__}: {exc}",
        }


__all__ = [
    "TOOLS_RESTRITAS_APROVACAO",
    "TOOLS_SCHEMA",
    "executar_tool",
]
