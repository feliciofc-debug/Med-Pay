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
from app.models.jarvis_memoria import JarvisMemoria, TipoMemoria
from app.models.lote import Lote, StatusLote
from app.models.pagamento import Pagamento, StatusPagamento
from app.models.plano import Plano, StatusAssinatura
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
    {
        "type": "function",
        "function": {
            "name": "diagnostico_plataforma",
            "description": (
                "Diagnóstico GERAL da saúde da plataforma agora: "
                "erros 24h, lotes travados, fichas em ERRO, taxa de "
                "devolução, clientes inativos (>15d sem lote), clientes "
                "em trial vencendo. Use quando o gestor perguntar "
                "'tudo bem?', 'algum problema?', 'algo travado?', "
                "'me dá um diagnóstico', 'tá tudo rodando?'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "identificar_problemas",
            "description": (
                "Análise PROATIVA: lista problemas que merecem atenção "
                "agora mesmo (lotes parados >48h, fichas em ERRO há mais "
                "de 24h, beneficiários com conta inválida, alta taxa "
                "de devolução por cliente). Cada item vem com severidade "
                "(critico/alerta/info) e ação sugerida. Use quando o "
                "gestor pedir 'me mostra o que tá ruim', 'o que precisa "
                "atenção', 'problemas', 'gargalos'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analise_cliente_360",
            "description": (
                "Visão 360° de UM cliente específico: plano, status de "
                "assinatura, trial, MRR, total processado no mês, lotes "
                "no mês, qtd de beneficiários ativos, taxa de erro do "
                "cliente, última atividade, saúde geral. Use quando o "
                "usuário pedir 'me fala tudo do hospital X', 'panorama "
                "do cliente Y', 'análise do Auris'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_parcial": {
                        "type": "string",
                        "description": (
                            "Trecho do nome do cliente (basta primeira palavra)"
                        ),
                    }
                },
                "required": ["nome_parcial"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tendencias_3_meses",
            "description": (
                "Compara mês atual com 2 meses anteriores: volume "
                "processado, qtd de lotes, taxa de erro, taxa de "
                "devolução. Mostra delta % e tendência (subindo, caindo, "
                "estável). Use quando o gestor perguntar 'como tamo "
                "comparado ao mês passado?', 'tendência', 'evolução', "
                "'comparativo'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pipeline_comercial",
            "description": (
                "Pipeline e métricas SaaS: total de clientes por status "
                "(TRIAL, ATIVO, INADIMPLENTE, SUSPENSO, CANCELADO), "
                "distribuição por plano, MRR atual estimado, trials "
                "vencendo em 7 dias. Use quando o gestor perguntar "
                "'MRR', 'faturamento SaaS', 'quantos clientes', "
                "'pipeline', 'trials vencendo', 'como tá a base'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ranking_hospitais",
            "description": (
                "Ranking dos hospitais por volume processado no mês: "
                "top N pelo valor pago, com taxa de erro e qtd de lotes. "
                "Use pra 'qual cliente fatura mais', 'top hospitais', "
                "'ranking de clientes'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limite": {
                        "type": "integer",
                        "description": "Top N (default 10, máx 20)",
                    }
                },
            },
        },
    },
    # =====================================================
    # MEMÓRIA PERSISTENTE
    # =====================================================
    {
        "type": "function",
        "function": {
            "name": "lembrar",
            "description": (
                "Salva uma memória persistente — fato, preferência, decisão "
                "ou nota — que VOCÊ (Jarvis) quer lembrar nas próximas "
                "conversas com este usuário. Use quando o usuário disser "
                "algo tipo 'anota que…', 'lembra disso…', 'pra próxima', "
                "ou quando você espontaneamente perceber algo importante "
                "que deve persistir além da conversa atual."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo": {
                        "type": "string",
                        "enum": ["PREFERENCIA", "FATO", "DECISAO", "NOTA"],
                        "description": (
                            "PREFERENCIA = jeito que ele gosta. "
                            "FATO = informação concreta da operação/cliente. "
                            "DECISAO = decisão estratégica tomada. "
                            "NOTA = observação solta."
                        ),
                    },
                    "conteudo": {
                        "type": "string",
                        "description": (
                            "Texto da memória (1-2 frases, claro). "
                            "Escreva em 3a pessoa: 'Felício prefere…' não 'você prefere…'."
                        ),
                    },
                    "tags": {
                        "type": "string",
                        "description": (
                            "Tags separadas por vírgula pra facilitar "
                            "recuperação (ex: 'auris,banco,pix'). Opcional."
                        ),
                    },
                    "relevancia": {
                        "type": "integer",
                        "description": (
                            "1-10. 10 = sempre presente no contexto. "
                            "Default 5."
                        ),
                    },
                },
                "required": ["tipo", "conteudo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_memorias",
            "description": (
                "Lista as memórias persistentes do usuário (opcionalmente "
                "filtrando por tipo ou tag). Use quando ele perguntar "
                "'do que você lembra?', 'o que você sabe sobre mim?', "
                "ou quando precisar revisar antes de decidir."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo": {
                        "type": "string",
                        "enum": ["PREFERENCIA", "FATO", "DECISAO", "NOTA"],
                    },
                    "tag": {
                        "type": "string",
                        "description": "Filtra memorias contendo essa tag",
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Quantas (default 20, max 50)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "esquecer",
            "description": (
                "Marca uma memória como inativa (soft-delete). Use quando "
                "o usuário disser 'esquece isso', 'descarta a anotação X', "
                "'isso não é mais verdade'. Pede o ID curto da memória "
                "(primeiros 8 chars) — peça pra listar antes se precisar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "memoria_id_curto": {
                        "type": "string",
                        "description": "Primeiros 8 chars do ID da memória",
                    }
                },
                "required": ["memoria_id_curto"],
            },
        },
    },
    # =====================================================
    # AÇÕES DE ESCRITA CONTROLADAS (exigem CONFIRMO)
    # =====================================================
    {
        "type": "function",
        "function": {
            "name": "marcar_beneficiario_inativo",
            "description": (
                "INATIVA um beneficiário (médico/prestador) — não aparecerá "
                "mais em novos lotes. EXIGE confirmação 'CONFIRMO' explícita "
                "do usuário no mesmo fluxo do aprovar_lote: 1) você diz "
                "'vou inativar X (CPF Y, hospital Z)? Responde CONFIRMO'. "
                "2) só chama essa tool se ele responder CONFIRMO/SIM INATIVAR. "
                "Apenas usuários com pode_aprovar_pagamento podem usar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "beneficiario_id_curto": {
                        "type": "string",
                        "description": "Primeiros 8 chars do ID do beneficiário",
                    },
                    "motivo": {
                        "type": "string",
                        "description": "Por que está inativando (vira nota de auditoria)",
                    },
                },
                "required": ["beneficiario_id_curto", "motivo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "renovar_trial_cliente",
            "description": (
                "Estende o trial de um cliente em N dias. EXIGE CONFIRMO "
                "explícito. Útil quando hospital pede mais tempo pra "
                "avaliar. Apenas ADMIN MedPag (cliente_id NULL) + "
                "pode_aprovar_pagamento usa."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cliente_nome_parcial": {
                        "type": "string",
                        "description": "Trecho do nome do cliente",
                    },
                    "dias": {
                        "type": "integer",
                        "description": "Quantos dias adicionar (max 90)",
                    },
                },
                "required": ["cliente_nome_parcial", "dias"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reprocessar_ficha",
            "description": (
                "Reseta uma ficha em ERRO/EXTRAIDA pra status RECEBIDA, "
                "forçando reprocessamento do OCR. EXIGE CONFIRMO. "
                "Use quando o usuário disser 'tenta de novo a ficha X' "
                "depois que você mostrou que ela tá em ERRO."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ficha_id_curto": {
                        "type": "string",
                        "description": "Primeiros 8 chars do ID da ficha",
                    }
                },
                "required": ["ficha_id_curto"],
            },
        },
    },
    # =====================================================
    # INSIGHT ESTRATÉGICO (compõe múltiplas métricas)
    # =====================================================
    {
        "type": "function",
        "function": {
            "name": "gerar_insight_estrategico",
            "description": (
                "Compõe um pacote DENSO de métricas pra análise estratégica: "
                "diagnóstico + pipeline + tendência + ranking + problemas — "
                "tudo num único retorno. Use quando o gestor pedir "
                "'me dá uma visão completa', 'quero analisar a operação', "
                "'me prepara pra reunião', 'overview executivo'. "
                "Depois disso, você compõe uma narrativa textual rica "
                "(3-5 parágrafos) explicando o que os números dizem e "
                "sugerindo ações."
            ),
            "parameters": {"type": "object", "properties": {}},
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
# Tools estratégicas (diagnóstico, 360, tendência, comercial)
# ============================================================


async def diagnostico_plataforma(
    db: AsyncSession, _user: User
) -> dict[str, Any]:
    """Visão GERAL da saúde da plataforma — pra Jarvis avisar problemas."""
    agora = datetime.now(UTC)
    ha_24h = agora - timedelta(hours=24)
    ha_48h = agora - timedelta(hours=48)
    ha_15d = agora - timedelta(days=15)
    em_7d = agora + timedelta(days=7)

    # Lotes em AGUARDANDO_REVISAO ha mais de 48h (travados)
    lotes_travados_q = await db.execute(
        select(func.count(Lote.id)).where(
            Lote.status == StatusLote.AGUARDANDO_REVISAO,
            Lote.created_at <= ha_48h,
        )
    )
    lotes_travados = int(lotes_travados_q.scalar_one())

    # Fichas em ERRO nas ultimas 24h
    fichas_erro_q = await db.execute(
        select(func.count(FichaPlantao.id)).where(
            FichaPlantao.status == StatusFicha.ERRO,
            FichaPlantao.created_at >= ha_24h,
        )
    )
    fichas_erro_24h = int(fichas_erro_q.scalar_one())

    # Total fichas processadas 24h -> taxa de sucesso OCR
    fichas_total_q = await db.execute(
        select(func.count(FichaPlantao.id)).where(
            FichaPlantao.created_at >= ha_24h
        )
    )
    fichas_total_24h = int(fichas_total_q.scalar_one())
    taxa_sucesso_ocr_pct = (
        ((fichas_total_24h - fichas_erro_24h) / fichas_total_24h * 100)
        if fichas_total_24h > 0
        else 100.0
    )

    # Devolucoes 24h
    devo_q = await db.execute(
        select(func.count(Pagamento.id)).where(
            Pagamento.status == StatusPagamento.NAO_PAGO,
            Pagamento.updated_at >= ha_24h,
        )
    )
    devo_24h = int(devo_q.scalar_one())

    # Clientes ATIVOS sem lote ha mais de 15 dias
    clientes_inativos_q = await db.execute(
        select(func.count(Cliente.id))
        .outerjoin(
            Lote,
            (Lote.cliente_id == Cliente.id) & (Lote.created_at >= ha_15d),
        )
        .where(
            Cliente.ativo.is_(True),
            Cliente.status_assinatura == StatusAssinatura.ATIVO,
        )
        .group_by(Cliente.id)
        .having(func.count(Lote.id) == 0)
    )
    clientes_inativos = len(list(clientes_inativos_q.all()))

    # Trials vencendo nos proximos 7 dias
    trials_q = await db.execute(
        select(func.count(Cliente.id)).where(
            Cliente.status_assinatura == StatusAssinatura.TRIAL,
            Cliente.trial_termina_em.isnot(None),
            Cliente.trial_termina_em <= em_7d,
            Cliente.trial_termina_em >= agora,
        )
    )
    trials_vencendo = int(trials_q.scalar_one())

    # Saude geral — heuristica simples
    flags = []
    if lotes_travados > 0:
        flags.append(f"{lotes_travados} lote(s) parado(s) há +48h")
    if taxa_sucesso_ocr_pct < 80 and fichas_total_24h > 5:
        flags.append(f"OCR caiu pra {taxa_sucesso_ocr_pct:.0f}% nas últimas 24h")
    if devo_24h > 10:
        flags.append(f"{devo_24h} devoluções nas últimas 24h (acima do baseline)")
    if clientes_inativos > 0:
        flags.append(f"{clientes_inativos} cliente(s) ativo(s) sem lote há +15d")
    if trials_vencendo > 0:
        flags.append(f"{trials_vencendo} trial(is) vencendo nos próximos 7d")

    saude = "ok" if not flags else ("alerta" if len(flags) <= 2 else "critico")

    return {
        "saude_geral": saude,
        "alertas": flags,
        "lotes_travados_48h": lotes_travados,
        "fichas_erro_24h": fichas_erro_24h,
        "fichas_total_24h": fichas_total_24h,
        "taxa_sucesso_ocr_24h_pct": round(taxa_sucesso_ocr_pct, 1),
        "devolucoes_24h": devo_24h,
        "clientes_ativos_inativos_15d": clientes_inativos,
        "trials_vencendo_7d": trials_vencendo,
    }


async def identificar_problemas(
    db: AsyncSession, _user: User
) -> dict[str, Any]:
    """Lista PROBLEMAS especificos com severidade e acao sugerida.

    Mais granular que diagnostico — entrega itens acionaveis.
    """
    agora = datetime.now(UTC)
    ha_48h = agora - timedelta(hours=48)
    ha_24h = agora - timedelta(hours=24)
    problemas: list[dict[str, Any]] = []

    # Lotes parados > 48h
    lotes_parados_q = await db.execute(
        select(Lote)
        .where(
            Lote.status == StatusLote.AGUARDANDO_REVISAO,
            Lote.created_at <= ha_48h,
        )
        .options(selectinload(Lote.cliente))
        .order_by(Lote.created_at.asc())
        .limit(5)
    )
    for lote in lotes_parados_q.scalars().all():
        horas = int((agora - lote.created_at).total_seconds() / 3600)
        problemas.append(
            {
                "severidade": "critico" if horas > 96 else "alerta",
                "tipo": "lote_parado",
                "descricao": (
                    f"Lote {str(lote.id)[:8]} de {lote.cliente.nome if lote.cliente else '?'} "
                    f"aguardando revisão há {horas}h"
                ),
                "valor_reais": lote.valor_total_centavos / 100,
                "acao_sugerida": "revisar e aprovar (ou cancelar) pelo painel",
            }
        )

    # Fichas em ERRO 24h
    fichas_erro_q = await db.execute(
        select(FichaPlantao)
        .where(
            FichaPlantao.status == StatusFicha.ERRO,
            FichaPlantao.created_at >= ha_24h,
        )
        .options(selectinload(FichaPlantao.cliente))
        .order_by(FichaPlantao.created_at.desc())
        .limit(5)
    )
    for ficha in fichas_erro_q.scalars().all():
        problemas.append(
            {
                "severidade": "alerta",
                "tipo": "ficha_erro",
                "descricao": (
                    f"Ficha {str(ficha.id)[:8]} de "
                    f"{ficha.cliente.nome if ficha.cliente else '?'} "
                    f"em ERRO ({ficha.mensagem_erro or 'sem msg'})"
                ),
                "acao_sugerida": "reprocessar OCR ou subir foto melhor",
            }
        )

    # Clientes com taxa de erro alta no mes
    inicio_mes = _ini_mes()
    erro_alto_q = await db.execute(
        select(
            Cliente.id,
            Cliente.nome,
            func.coalesce(func.sum(Lote.total_pagamentos), 0).label("total"),
            func.coalesce(func.sum(Lote.total_bloqueados), 0).label("bloq"),
        )
        .join(Lote, Lote.cliente_id == Cliente.id)
        .where(Lote.created_at >= inicio_mes)
        .group_by(Cliente.id, Cliente.nome)
        .having(func.coalesce(func.sum(Lote.total_pagamentos), 0) >= 20)
        .order_by(desc("bloq"))
        .limit(5)
    )
    for row in erro_alto_q.all():
        total = int(row.total)
        bloq = int(row.bloq)
        taxa = (bloq / total * 100) if total else 0
        if taxa >= 10:
            problemas.append(
                {
                    "severidade": "critico" if taxa >= 25 else "alerta",
                    "tipo": "taxa_erro_cliente",
                    "descricao": (
                        f"{row.nome} com taxa de erro {taxa:.0f}% no mês "
                        f"({bloq} bloqueados em {total} pagamentos)"
                    ),
                    "acao_sugerida": (
                        "revisar cadastro de beneficiários do cliente; "
                        "muito provavelmente CPF/conta desatualizados"
                    ),
                }
            )

    if not problemas:
        problemas.append(
            {
                "severidade": "info",
                "tipo": "tudo_ok",
                "descricao": "Nenhum problema crítico identificado agora.",
                "acao_sugerida": "",
            }
        )

    return {
        "total": len(problemas),
        "criticos": sum(1 for p in problemas if p["severidade"] == "critico"),
        "alertas": sum(1 for p in problemas if p["severidade"] == "alerta"),
        "problemas": problemas,
    }


async def analise_cliente_360(
    db: AsyncSession, _user: User, *, nome_parcial: str
) -> dict[str, Any]:
    """View 360 graus de um cliente — plano, MRR, operacao, saude."""
    from app.models.beneficiario import Beneficiario, StatusBeneficiario

    s = (nome_parcial or "").strip()
    if not s or len(s) < 2:
        return {"erro": "consulta_curta", "mensagem": "Nome muito curto"}

    cliente_q = await db.execute(
        select(Cliente)
        .where(Cliente.nome.ilike(f"%{s}%"))
        .options(selectinload(Cliente.plano))
        .limit(1)
    )
    cliente = cliente_q.scalar_one_or_none()
    if not cliente:
        return {
            "erro": "nao_encontrado",
            "mensagem": f"Nenhum cliente com '{s}' no nome.",
        }

    inicio_mes = _ini_mes()

    # Stats do mes
    stats_q = await db.execute(
        select(
            func.count(Lote.id).label("lotes"),
            func.coalesce(func.sum(Lote.valor_total_centavos), 0).label("valor"),
            func.coalesce(func.sum(Lote.total_pagamentos), 0).label("pgs"),
            func.coalesce(func.sum(Lote.total_bloqueados), 0).label("bloq"),
            func.max(Lote.created_at).label("ultima"),
        ).where(
            Lote.cliente_id == cliente.id,
            Lote.created_at >= inicio_mes,
        )
    )
    stats = stats_q.one()
    pgs = int(stats.pgs)
    bloq = int(stats.bloq)
    taxa_erro = (bloq / pgs * 100) if pgs else 0

    # Beneficiarios ativos
    benef_q = await db.execute(
        select(
            func.count(Beneficiario.id).filter(
                Beneficiario.status == StatusBeneficiario.ATIVO
            ),
            func.count(Beneficiario.id).filter(
                Beneficiario.status == StatusBeneficiario.PENDENTE
            ),
            func.count(Beneficiario.id).filter(
                Beneficiario.conta_verificada.is_(False)
                & Beneficiario.conta_invalida_motivo.isnot(None)
            ),
        ).where(Beneficiario.cliente_id == cliente.id)
    )
    benef_ativos, benef_pendentes, benef_conta_ruim = benef_q.one()

    # Heuristica de saude
    flags = []
    if stats.ultima and (datetime.now(UTC) - stats.ultima).days > 15:
        flags.append(f"sem lote há {(datetime.now(UTC) - stats.ultima).days}d")
    if taxa_erro >= 10:
        flags.append(f"taxa de erro alta ({taxa_erro:.0f}%)")
    if benef_conta_ruim and benef_conta_ruim > 5:
        flags.append(f"{benef_conta_ruim} beneficiários com conta inválida")
    if cliente.status_assinatura == StatusAssinatura.INADIMPLENTE:
        flags.append("assinatura INADIMPLENTE")
    if cliente.status_assinatura == StatusAssinatura.TRIAL:
        if cliente.trial_termina_em:
            dias = (cliente.trial_termina_em - datetime.now(UTC)).days
            if dias <= 7:
                flags.append(f"trial vence em {dias}d")

    saude = "ok" if not flags else ("alerta" if len(flags) <= 1 else "critico")

    return {
        "id": str(cliente.id),
        "nome": cliente.nome,
        "cnpj": cliente.cnpj,
        "plano": cliente.plano.nome if cliente.plano else "—",
        "plano_slug": cliente.plano.slug if cliente.plano else "—",
        "mensalidade_reais": (
            cliente.plano.preco_mensal_centavos / 100 if cliente.plano else 0
        ),
        "status_assinatura": cliente.status_assinatura.value,
        "trial_termina_em": (
            cliente.trial_termina_em.isoformat()
            if cliente.trial_termina_em
            else None
        ),
        "lotes_mes": int(stats.lotes),
        "valor_processado_mes_reais": float(stats.valor) / 100,
        "pagamentos_mes": pgs,
        "taxa_erro_pct": round(taxa_erro, 1),
        "ultima_atividade": (
            stats.ultima.isoformat() if stats.ultima else None
        ),
        "beneficiarios_ativos": int(benef_ativos),
        "beneficiarios_pendentes": int(benef_pendentes),
        "beneficiarios_conta_invalida": int(benef_conta_ruim or 0),
        "saude": saude,
        "flags": flags,
    }


async def tendencias_3_meses(
    db: AsyncSession, _user: User
) -> dict[str, Any]:
    """Compara mes atual com 2 meses anteriores."""
    agora = datetime.now(UTC)

    def _intervalo_mes(offset: int) -> tuple[datetime, datetime, str]:
        """offset 0 = mes atual; 1 = mes passado; 2 = retrasado."""
        ano = agora.year
        mes = agora.month - offset
        while mes <= 0:
            mes += 12
            ano -= 1
        inicio = datetime(ano, mes, 1, tzinfo=UTC)
        if mes == 12:
            fim = datetime(ano + 1, 1, 1, tzinfo=UTC)
        else:
            fim = datetime(ano, mes + 1, 1, tzinfo=UTC)
        return inicio, fim, f"{mes:02d}/{ano}"

    async def _stats(inicio: datetime, fim: datetime) -> dict[str, Any]:
        q = await db.execute(
            select(
                func.count(Lote.id),
                func.coalesce(func.sum(Lote.valor_total_centavos), 0),
                func.coalesce(func.sum(Lote.total_pagamentos), 0),
                func.coalesce(func.sum(Lote.total_bloqueados), 0),
            ).where(
                Lote.created_at >= inicio,
                Lote.created_at < fim,
            )
        )
        lotes, valor, pgs, bloq = q.one()
        pgs_i = int(pgs)
        return {
            "lotes": int(lotes),
            "valor_reais": float(valor) / 100,
            "pagamentos": pgs_i,
            "taxa_erro_pct": (int(bloq) / pgs_i * 100) if pgs_i else 0,
        }

    meses = []
    for offset in (2, 1, 0):  # cronologico
        inicio, fim, label = _intervalo_mes(offset)
        s = await _stats(inicio, fim)
        s["mes"] = label
        meses.append(s)

    # Calcula tendencia (mes atual vs anterior)
    if meses[2]["valor_reais"] and meses[1]["valor_reais"]:
        delta_pct = (
            (meses[2]["valor_reais"] - meses[1]["valor_reais"])
            / meses[1]["valor_reais"]
            * 100
        )
        if delta_pct > 5:
            tendencia = "subindo"
        elif delta_pct < -5:
            tendencia = "caindo"
        else:
            tendencia = "estavel"
    else:
        delta_pct = 0
        tendencia = "indefinida"

    return {
        "meses": meses,
        "delta_valor_pct": round(delta_pct, 1),
        "tendencia": tendencia,
    }


async def pipeline_comercial(
    db: AsyncSession, _user: User
) -> dict[str, Any]:
    """Pipeline SaaS: clientes por status, plano, MRR, trials vencendo."""
    agora = datetime.now(UTC)
    em_7d = agora + timedelta(days=7)

    # Clientes por status
    status_q = await db.execute(
        select(Cliente.status_assinatura, func.count(Cliente.id))
        .where(Cliente.ativo.is_(True))
        .group_by(Cliente.status_assinatura)
    )
    por_status = {s.value: int(n) for s, n in status_q.all()}

    # Clientes por plano + MRR estimado (so clientes ATIVO)
    plano_q = await db.execute(
        select(
            Plano.slug,
            Plano.nome,
            Plano.preco_mensal_centavos,
            func.count(Cliente.id).label("qtd"),
        )
        .join(Cliente, Cliente.plano_id == Plano.id)
        .where(
            Cliente.ativo.is_(True),
            Cliente.status_assinatura == StatusAssinatura.ATIVO,
        )
        .group_by(Plano.slug, Plano.nome, Plano.preco_mensal_centavos)
        .order_by(desc("qtd"))
    )
    por_plano = []
    mrr_centavos = 0
    for row in plano_q.all():
        qtd = int(row.qtd)
        mrr_centavos += qtd * int(row.preco_mensal_centavos)
        por_plano.append(
            {
                "slug": row.slug,
                "nome": row.nome,
                "qtd": qtd,
                "preco_unit_reais": int(row.preco_mensal_centavos) / 100,
                "mrr_plano_reais": qtd * int(row.preco_mensal_centavos) / 100,
            }
        )

    # Trials vencendo em 7d
    trials_q = await db.execute(
        select(Cliente.id, Cliente.nome, Cliente.trial_termina_em)
        .where(
            Cliente.status_assinatura == StatusAssinatura.TRIAL,
            Cliente.trial_termina_em.isnot(None),
            Cliente.trial_termina_em <= em_7d,
            Cliente.trial_termina_em >= agora,
        )
        .order_by(Cliente.trial_termina_em.asc())
    )
    trials_vencendo = []
    for row in trials_q.all():
        dias = (row.trial_termina_em - agora).days
        trials_vencendo.append(
            {
                "id": str(row.id),
                "nome": row.nome,
                "vence_em_dias": dias,
            }
        )

    return {
        "total_clientes_ativos": sum(por_status.values()),
        "por_status": por_status,
        "por_plano": por_plano,
        "mrr_estimado_reais": mrr_centavos / 100,
        "arr_estimado_reais": mrr_centavos * 12 / 100,
        "trials_vencendo_7d": trials_vencendo,
    }


async def ranking_hospitais(
    db: AsyncSession, _user: User, *, limite: int = 10
) -> dict[str, Any]:
    """Top N hospitais por volume processado no mes."""
    limite = max(1, min(int(limite or 10), 20))
    inicio = _ini_mes()
    result = await db.execute(
        select(
            Cliente.id,
            Cliente.nome,
            func.count(Lote.id).label("lotes"),
            func.coalesce(func.sum(Lote.total_pagamentos), 0).label("pgs"),
            func.coalesce(func.sum(Lote.total_bloqueados), 0).label("bloq"),
            func.coalesce(func.sum(Lote.valor_total_centavos), 0).label("valor"),
        )
        .join(Lote, Lote.cliente_id == Cliente.id)
        .where(Lote.created_at >= inicio)
        .group_by(Cliente.id, Cliente.nome)
        .order_by(desc("valor"))
        .limit(limite)
    )
    hospitais = []
    for row in result.all():
        pgs = int(row.pgs)
        bloq = int(row.bloq)
        hospitais.append(
            {
                "id": str(row.id),
                "nome": row.nome,
                "lotes": int(row.lotes),
                "pagamentos": pgs,
                "bloqueados": bloq,
                "taxa_erro_pct": round((bloq / pgs * 100) if pgs else 0, 1),
                "valor_total_reais": float(row.valor) / 100,
            }
        )
    return {
        "mes": inicio.strftime("%m/%Y"),
        "total": len(hospitais),
        "hospitais": hospitais,
    }


# ============================================================
# Memória persistente
# ============================================================


async def lembrar(
    db: AsyncSession,
    user: User,
    *,
    tipo: str,
    conteudo: str,
    tags: str | None = None,
    relevancia: int = 5,
) -> dict[str, Any]:
    """Salva um item de memória pro Jarvis usar em futuras conversas."""
    try:
        tipo_enum = TipoMemoria(tipo.upper())
    except ValueError:
        return {
            "erro": "tipo_invalido",
            "mensagem": "tipo precisa ser PREFERENCIA, FATO, DECISAO ou NOTA",
        }

    conteudo = (conteudo or "").strip()
    if not conteudo or len(conteudo) < 3:
        return {"erro": "vazio", "mensagem": "conteudo curto demais"}

    rel = max(1, min(int(relevancia or 5), 10))
    memoria = JarvisMemoria(
        user_id=user.id,
        tipo=tipo_enum,
        conteudo=conteudo[:2000],
        tags=tags[:255] if tags else None,
        relevancia=rel,
    )
    db.add(memoria)
    await db.flush()
    return {
        "sucesso": True,
        "id_curto": str(memoria.id)[:8],
        "tipo": tipo_enum.value,
        "mensagem": f"Memória salva como {tipo_enum.value} (rel {rel}/10)",
    }


async def listar_memorias(
    db: AsyncSession,
    user: User,
    *,
    tipo: str | None = None,
    tag: str | None = None,
    limite: int = 20,
) -> dict[str, Any]:
    """Lista memorias ativas do usuario, ordenadas por relevancia desc."""
    limite = max(1, min(int(limite or 20), 50))
    q = (
        select(JarvisMemoria)
        .where(
            JarvisMemoria.user_id == user.id,
            JarvisMemoria.ativa.is_(True),
        )
        .order_by(
            desc(JarvisMemoria.relevancia),
            desc(JarvisMemoria.updated_at),
        )
        .limit(limite)
    )
    if tipo:
        try:
            q = q.where(JarvisMemoria.tipo == TipoMemoria(tipo.upper()))
        except ValueError:
            return {"erro": "tipo_invalido"}
    if tag:
        q = q.where(JarvisMemoria.tags.ilike(f"%{tag}%"))

    result = await db.execute(q)
    memorias = list(result.scalars().all())
    return {
        "total": len(memorias),
        "memorias": [
            {
                "id_curto": str(m.id)[:8],
                "tipo": m.tipo.value,
                "conteudo": m.conteudo,
                "tags": m.tags,
                "relevancia": m.relevancia,
                "criada_em": m.created_at.isoformat(),
            }
            for m in memorias
        ],
    }


async def esquecer(
    db: AsyncSession, user: User, *, memoria_id_curto: str
) -> dict[str, Any]:
    """Soft-delete de uma memoria."""
    s = (memoria_id_curto or "").strip().lower()
    if not s:
        return {"erro": "id_vazio"}

    result = await db.execute(
        select(JarvisMemoria)
        .where(
            JarvisMemoria.user_id == user.id,
            JarvisMemoria.ativa.is_(True),
            sa.cast(JarvisMemoria.id, String).ilike(f"{s}%"),
        )
        .limit(2)
    )
    rows = list(result.scalars().all())
    if not rows:
        return {"erro": "nao_encontrada", "mensagem": f"sem memoria '{s}'"}
    if len(rows) > 1:
        return {
            "erro": "ambigua",
            "mensagem": "mais de uma memoria casa esse prefixo; use mais chars",
        }
    rows[0].ativa = False
    await db.flush()
    return {
        "sucesso": True,
        "id_curto": str(rows[0].id)[:8],
        "mensagem": f"Esqueci: '{rows[0].conteudo[:80]}'",
    }


async def carregar_memorias_para_prompt(
    db: AsyncSession, user: User, *, limite: int = 20
) -> list[JarvisMemoria]:
    """Helper consumido pelo `jarvis_agent.py` ao montar system prompt."""
    result = await db.execute(
        select(JarvisMemoria)
        .where(
            JarvisMemoria.user_id == user.id,
            JarvisMemoria.ativa.is_(True),
        )
        .order_by(
            desc(JarvisMemoria.relevancia),
            desc(JarvisMemoria.updated_at),
        )
        .limit(limite)
    )
    return list(result.scalars().all())


# ============================================================
# Ações de escrita (exigem CONFIRMO)
# ============================================================


async def marcar_beneficiario_inativo(
    db: AsyncSession,
    user: User,
    *,
    beneficiario_id_curto: str,
    motivo: str,
) -> dict[str, Any]:
    from app.models.auditoria import Auditoria
    from app.models.beneficiario import Beneficiario, StatusBeneficiario

    s = (beneficiario_id_curto or "").strip().lower()
    if not s or len(s) < 4:
        return {"erro": "id_curto", "mensagem": "preciso de pelo menos 4 chars do ID"}
    if not motivo or len(motivo) < 5:
        return {"erro": "motivo_vazio", "mensagem": "preciso de motivo (mín 5 chars)"}

    result = await db.execute(
        select(Beneficiario)
        .where(sa.cast(Beneficiario.id, String).ilike(f"{s}%"))
        .limit(2)
    )
    rows = list(result.scalars().all())
    if not rows:
        return {"erro": "nao_encontrado"}
    if len(rows) > 1:
        return {"erro": "ambiguo", "mensagem": "+ de 1 casa esse prefixo"}

    benef = rows[0]
    # Tenant check: se user é hospital, só pode mexer no próprio
    if user.cliente_id and benef.cliente_id != user.cliente_id:
        return {"erro": "permissao", "mensagem": "beneficiario de outro hospital"}

    if benef.status == StatusBeneficiario.INATIVO:
        return {"erro": "ja_inativo", "mensagem": "já está inativo"}

    benef.status = StatusBeneficiario.INATIVO
    audit = Auditoria(
        acao="beneficiario_inativado_jarvis",
        entidade_tipo="beneficiario",
        entidade_id=benef.id,
        user_id=user.id,
        detalhes={"motivo": motivo, "via": "jarvis_whatsapp"},
    )
    db.add(audit)
    await db.flush()
    return {
        "sucesso": True,
        "beneficiario_id": str(benef.id)[:8],
        "nome": benef.nome,
        "mensagem": f"Beneficiário {benef.nome} marcado como INATIVO",
    }


async def renovar_trial_cliente(
    db: AsyncSession,
    user: User,
    *,
    cliente_nome_parcial: str,
    dias: int,
) -> dict[str, Any]:
    from app.models.auditoria import Auditoria

    # Só MedPag interno (ADMIN sem cliente_id) pode
    if user.cliente_id is not None or user.role != UserRole.ADMIN:
        return {
            "erro": "permissao",
            "mensagem": "só ADMIN MedPag pode renovar trial",
        }
    dias = max(1, min(int(dias or 0), 90))
    s = (cliente_nome_parcial or "").strip()
    if not s or len(s) < 2:
        return {"erro": "nome_curto"}

    result = await db.execute(
        select(Cliente).where(Cliente.nome.ilike(f"%{s}%")).limit(2)
    )
    rows = list(result.scalars().all())
    if not rows:
        return {"erro": "nao_encontrado"}
    if len(rows) > 1:
        return {
            "erro": "ambiguo",
            "mensagem": "+ de 1 cliente casa; seja específico",
        }

    cliente = rows[0]
    agora = datetime.now(UTC)
    base = (
        cliente.trial_termina_em
        if cliente.trial_termina_em and cliente.trial_termina_em > agora
        else agora
    )
    nova_data = base + timedelta(days=dias)
    cliente.trial_termina_em = nova_data
    if cliente.status_assinatura != StatusAssinatura.TRIAL:
        cliente.status_assinatura = StatusAssinatura.TRIAL

    audit = Auditoria(
        acao="trial_renovado_jarvis",
        entidade_tipo="cliente",
        entidade_id=cliente.id,
        user_id=user.id,
        detalhes={
            "dias_adicionados": dias,
            "nova_data_fim": nova_data.isoformat(),
            "via": "jarvis_whatsapp",
        },
    )
    db.add(audit)
    await db.flush()
    return {
        "sucesso": True,
        "cliente": cliente.nome,
        "dias_adicionados": dias,
        "novo_fim_trial": nova_data.strftime("%d/%m/%Y"),
        "mensagem": (
            f"Trial de {cliente.nome} estendido por +{dias}d, "
            f"agora vence em {nova_data.strftime('%d/%m/%Y')}"
        ),
    }


async def reprocessar_ficha(
    db: AsyncSession,
    user: User,
    *,
    ficha_id_curto: str,
) -> dict[str, Any]:
    s = (ficha_id_curto or "").strip().lower()
    if not s or len(s) < 4:
        return {"erro": "id_curto"}

    result = await db.execute(
        select(FichaPlantao)
        .where(sa.cast(FichaPlantao.id, String).ilike(f"{s}%"))
        .limit(2)
    )
    rows = list(result.scalars().all())
    if not rows:
        return {"erro": "nao_encontrada"}
    if len(rows) > 1:
        return {"erro": "ambigua"}
    ficha = rows[0]

    if user.cliente_id and ficha.cliente_id != user.cliente_id:
        return {"erro": "permissao", "mensagem": "ficha de outro hospital"}

    if ficha.status not in (StatusFicha.ERRO, StatusFicha.EXTRAIDA):
        return {
            "erro": "status_invalido",
            "mensagem": f"ficha em {ficha.status.value}, só reprocesso ERRO/EXTRAIDA",
        }

    ficha.status = StatusFicha.RECEBIDA
    ficha.mensagem_erro = None
    await db.flush()
    # Por enquanto só reseta o status — o processamento OCR ainda
    # acontece via upload manual (ou via celery quando criarmos a task
    # `processar_ficha` dedicada). Coordenador vê a ficha como
    # RECEBIDA e pode reprocessar pelo painel.
    return {
        "sucesso": True,
        "ficha_id": str(ficha.id)[:8],
        "mensagem": "Ficha resetada pra RECEBIDA — reprocessa pelo painel.",
    }


# ============================================================
# Insight estratégico (compõe múltiplas tools)
# ============================================================


async def gerar_insight_estrategico(
    db: AsyncSession, user: User
) -> dict[str, Any]:
    """Pacote denso pra Jarvis fazer análise narrativa."""
    diag = await diagnostico_plataforma(db, user)
    pipe = await pipeline_comercial(db, user)
    tend = await tendencias_3_meses(db, user)
    rank = await ranking_hospitais(db, user, limite=5)
    probs = await identificar_problemas(db, user)
    return {
        "diagnostico": diag,
        "pipeline": pipe,
        "tendencia": tend,
        "top_hospitais": rank,
        "problemas": probs,
        "instrucao": (
            "Compõe agora uma narrativa rica (3-5 parágrafos curtos) "
            "explicando: 1) como está a saúde geral, 2) como o comercial "
            "está performando (MRR, trials), 3) tendência (subindo/caindo "
            "e por quê), 4) quais hospitais merecem atenção e 5) prox "
            "ações sugeridas. Se quiser, oferece salvar conclusões "
            "como DECISAO via lembrar()."
        ),
    }


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
    "diagnostico_plataforma": diagnostico_plataforma,
    "identificar_problemas": identificar_problemas,
    "analise_cliente_360": analise_cliente_360,
    "tendencias_3_meses": tendencias_3_meses,
    "pipeline_comercial": pipeline_comercial,
    "ranking_hospitais": ranking_hospitais,
    "lembrar": lembrar,
    "listar_memorias": listar_memorias,
    "esquecer": esquecer,
    "marcar_beneficiario_inativo": marcar_beneficiario_inativo,
    "renovar_trial_cliente": renovar_trial_cliente,
    "reprocessar_ficha": reprocessar_ficha,
    "gerar_insight_estrategico": gerar_insight_estrategico,
}


# Tools que exigem `pode_aprovar_pagamento=True` no WhatsAppUser.
# Se o usuário não tiver a flag, essas tools são filtradas do schema
# antes da chamada ao LLM (ele nem enxerga elas).
TOOLS_RESTRITAS_APROVACAO: frozenset[str] = frozenset(
    {
        "aprovar_lote",
        "marcar_beneficiario_inativo",
        "renovar_trial_cliente",
        "reprocessar_ficha",
    }
)


async def executar_tool(
    db: AsyncSession,
    user: User,
    *,
    nome: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Despacha o tool_call do LLM para a função Python correspondente.

    Cada tool roda dentro de um SAVEPOINT (`begin_nested`) — assim, se
    uma query falhar (ex: tabela inexistente, FK inválida), o rollback
    isolado mantém a sessão principal limpa e as próximas tools e o
    fluxo do agent seguem normalmente. Sempre retorna dict JSON-safe.
    """
    func_alvo = _DISPATCH.get(nome)
    if func_alvo is None:
        return {"erro": "tool_desconhecida", "mensagem": f"Tool '{nome}' não existe."}

    try:
        async with db.begin_nested():
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
