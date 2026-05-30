"""Agente Jarvis — LLM (Groq) + tools + memória curta + audit.

Fluxo de uma mensagem inbound:

    1. `processar_mensagem(numero, texto, message_id)` é chamado pelo
       webhook do Wuzapi.
    2. Verifica se número está no whitelist (`WhatsAppUser`). Se não,
       grava a mensagem com `user_id=NULL` + `erro="numero_nao_autorizado"`
       e retorna texto de aviso (que NÃO é enviado — política de não
       responder pra estranhos).
    3. Carrega contexto: últimas N mensagens das últimas H horas.
    4. Monta system prompt com role do usuário e permissões.
    5. Loop de tool calling:
       - chama Groq com mensagens + tools_schema
       - se resposta tem tool_calls, executa e adiciona resultado
       - até no máximo 5 iterações (proteção contra loop)
    6. Retorna texto final pra enviar.
    7. Persiste mensagem inbound + outbound + tools usadas + tokens.

Filosofia de prompt: o "system prompt" carrega a inteligência. A IA é
um sócio do MedPag, sabe da operação, conhece os termos técnicos
(CNAB, lote, beneficiário), responde em português brasileiro casual
e direto. Não inventa números — sempre busca via tool.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import MedPagException
from app.models.user import User
from app.models.whatsapp import (
    DirecaoMensagem,
    WhatsAppMensagem,
    WhatsAppUser,
)
from app.services.jarvis_kb import montar_system_prompt_enxuto
from app.services.jarvis_tools import (
    TOOLS_RESTRITAS_APROVACAO,
    TOOLS_SCHEMA,
    carregar_memorias_para_prompt,
    executar_tool,
)

log = structlog.get_logger()


class GroqIndisponivelError(MedPagException):
    code = "GROQ_INDISPONIVEL"
    status_code = 503


class JarvisFalhouError(MedPagException):
    code = "JARVIS_FALHOU"
    status_code = 500


# ============================================================
# System prompt — usa o KB rico em jarvis_kb.py
# ============================================================


async def _system_prompt_para(
    db: AsyncSession,
    user: User,
    *,
    pode_aprovar: bool,
) -> str:
    """Monta o system prompt completo (KB Med-Pay + contexto + memorias).

    O KB com identidade, stack, modulos, planos, roles, fluxo, glossario
    e como_responder fica em jarvis_kb.py. Aqui injetamos o contexto de
    QUEM esta conversando agora E as memorias persistentes desse user.
    """
    contexto_usuario = (
        "# Quem está conversando com você agora\n"
        f"- Nome: {user.nome}\n"
        f"- Email: {user.email}\n"
        f"- Role: {user.role.value}\n"
        f"- Hospital: "
        + (user.cliente.nome if user.cliente else "MedPag interno (você fala com MedPag)")
        + "\n"
        f"- Pode aprovar lote via WhatsApp: {'SIM' if pode_aprovar else 'NÃO'}\n"
        f"- Hora atual (UTC): {datetime.now(UTC).isoformat()}\n"
    )
    if not pode_aprovar:
        contexto_usuario += (
            "\nObservação: como ele NÃO tem flag de aprovação, se pedir "
            "'aprovar lote' você explica que essa ação precisa ser feita "
            "pelo painel web ou por um sócio autorizado, sem chamar a tool.\n"
        )
    if user.cliente:
        contexto_usuario += (
            f"\nIMPORTANTE: este usuário enxerga APENAS dados do hospital "
            f"'{user.cliente.nome}'. As tools que você chamar ja filtram "
            "pelo tenant dele automaticamente.\n"
        )
    else:
        contexto_usuario += (
            "\nIMPORTANTE: este usuário é MedPag INTERNO — vê dados de "
            "TODOS os hospitais. Sinta-se à vontade pra trazer comparativos, "
            "rankings, panorama agregado.\n"
        )

    # Memórias persistentes — entram como bloco extra do prompt.
    # IMPORTANTE: usamos SAVEPOINT (begin_nested) pra isolar essa query.
    # Se a tabela ainda não existe no banco (migration 022 não aplicada)
    # ou qualquer outro erro, o rollback do savepoint mantém a sessão
    # principal limpa pra continuar processando o resto do fluxo.
    memorias_bloco = ""
    memorias: list = []
    try:
        async with db.begin_nested():
            memorias = await carregar_memorias_para_prompt(
                db, user, limite=20
            )
    except Exception:  # noqa: BLE001
        log.warning("jarvis.carregar_memorias_falhou", exc_info=True)
        memorias = []

    if memorias:
        linhas = ["# Memórias persistentes (coisas que você lembra desse usuário)"]
        linhas.append(
            "Use isto como CONTEXTO de longo prazo. Se algo aqui parecer "
            "desatualizado, sugira esquecer (use a tool 'esquecer'). Se quiser "
            "guardar algo novo, use 'lembrar'."
        )
        for m in memorias:
            tags = f" [{m.tags}]" if m.tags else ""
            linhas.append(
                f"- ({m.tipo.value} rel{m.relevancia}/10){tags} "
                f"id={str(m.id)[:8]}: {m.conteudo}"
            )
        memorias_bloco = "\n".join(linhas)

    return montar_system_prompt_enxuto(contexto_usuario, memorias_bloco)


# ============================================================
# Cliente Groq (lazy)
# ============================================================


def _groq_client():  # type: ignore[no-untyped-def]
    """Importa e instancia o client Groq sob demanda.

    Lazy pra não forçar `groq` no requirements em ambientes que não
    usam o módulo (tests, dev local sem chave).
    """
    if not settings.GROQ_API_KEY:
        raise GroqIndisponivelError(
            "GROQ_API_KEY não configurada. Crie chave em "
            "https://console.groq.com/keys"
        )
    try:
        from groq import AsyncGroq
    except ImportError as exc:  # pragma: no cover
        raise GroqIndisponivelError(
            "Pacote 'groq' não instalado — adicione ao requirements.txt"
        ) from exc
    return AsyncGroq(api_key=settings.GROQ_API_KEY)


# ============================================================
# Resultado
# ============================================================


@dataclass(slots=True)
class JarvisResultado:
    texto_resposta: str
    tools_usadas: list[dict[str, Any]]
    tokens_prompt: int
    tokens_resposta: int
    duracao_ms: int


# ============================================================
# Histórico
# ============================================================


async def _carregar_historico(
    db: AsyncSession,
    *,
    numero_e164: str,
    horas: int,
    limite: int,
) -> list[dict[str, str]]:
    """Recupera mensagens recentes da conversa pra dar contexto ao LLM.

    Retorna em ordem cronológica (antiga → recente), formato OpenAI.
    """
    desde = datetime.now(UTC) - timedelta(hours=horas)
    result = await db.execute(
        select(WhatsAppMensagem)
        .where(
            WhatsAppMensagem.numero_e164 == numero_e164,
            WhatsAppMensagem.created_at >= desde,
            WhatsAppMensagem.erro.is_(None),
        )
        .order_by(desc(WhatsAppMensagem.created_at))
        .limit(limite)
    )
    msgs = list(result.scalars().all())
    msgs.reverse()  # cronológico

    historico: list[dict[str, str]] = []
    for msg in msgs:
        role = "user" if msg.direcao == DirecaoMensagem.INBOUND else "assistant"
        historico.append({"role": role, "content": msg.texto})
    return historico


# ============================================================
# Loop principal
# ============================================================


MAX_ITERACOES_TOOL = 8  # antes 5 — mais espaco pra investigacoes profundas


async def _chamar_llm(
    *,
    messages: list[dict[str, Any]],
    tools_disponiveis: list[dict[str, Any]],
) -> Any:
    client = _groq_client()
    return await client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=messages,
        tools=tools_disponiveis,
        tool_choice="auto",
        temperature=settings.GROQ_TEMPERATURE,
        max_tokens=settings.GROQ_MAX_TOKENS,
    )


async def _gerar_resposta(
    db: AsyncSession,
    *,
    user: User,
    pode_aprovar: bool,
    texto_usuario: str,
    historico: list[dict[str, str]],
) -> JarvisResultado:
    """Roda o loop tool-calling até o LLM produzir resposta final."""
    inicio = time.monotonic()

    # Filtra tools que o usuário tem permissão de usar
    tools_disponiveis = [
        t
        for t in TOOLS_SCHEMA
        if (
            t["function"]["name"] not in TOOLS_RESTRITAS_APROVACAO
            or pode_aprovar
        )
    ]

    system_text = await _system_prompt_para(
        db, user, pode_aprovar=pode_aprovar
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_text},
    ]
    messages.extend(historico)
    messages.append({"role": "user", "content": texto_usuario})

    tools_usadas: list[dict[str, Any]] = []
    tokens_prompt = 0
    tokens_resposta = 0

    for iteracao in range(MAX_ITERACOES_TOOL):
        try:
            response = await _chamar_llm(
                messages=messages, tools_disponiveis=tools_disponiveis
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("jarvis.groq_falhou", iteracao=iteracao)
            raise JarvisFalhouError(
                f"Falha no Groq: {type(exc).__name__}: {exc}"
            ) from exc

        choice = response.choices[0]
        if response.usage:
            tokens_prompt += int(getattr(response.usage, "prompt_tokens", 0) or 0)
            tokens_resposta += int(
                getattr(response.usage, "completion_tokens", 0) or 0
            )

        msg = choice.message
        tool_calls = getattr(msg, "tool_calls", None)

        # Sem tool_calls → resposta final
        if not tool_calls:
            texto_final = (msg.content or "").strip()
            if not texto_final:
                texto_final = (
                    "Desculpe, não consegui formular uma resposta. "
                    "Tenta reformular a pergunta?"
                )
            duracao_ms = int((time.monotonic() - inicio) * 1000)
            return JarvisResultado(
                texto_resposta=texto_final,
                tools_usadas=tools_usadas,
                tokens_prompt=tokens_prompt,
                tokens_resposta=tokens_resposta,
                duracao_ms=duracao_ms,
            )

        # Adiciona a mensagem do assistant com tool_calls
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )

        # Executa cada tool e adiciona resultado
        for tc in tool_calls:
            nome = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            resultado = await executar_tool(db, user, nome=nome, args=args)
            tools_usadas.append(
                {"tool": nome, "args": args, "resultado": resultado}
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": nome,
                    "content": json.dumps(resultado, ensure_ascii=False),
                }
            )

    # Estourou o limite de iterações
    duracao_ms = int((time.monotonic() - inicio) * 1000)
    return JarvisResultado(
        texto_resposta=(
            "Tive dificuldade pra concluir essa consulta agora. "
            "Pode tentar reformular ou me pedir algo mais específico?"
        ),
        tools_usadas=tools_usadas,
        tokens_prompt=tokens_prompt,
        tokens_resposta=tokens_resposta,
        duracao_ms=duracao_ms,
    )


# ============================================================
# Whitelist + persistência
# ============================================================


async def _resolver_usuario(
    db: AsyncSession, numero_e164: str
) -> WhatsAppUser | None:
    result = await db.execute(
        select(WhatsAppUser)
        .where(
            WhatsAppUser.numero_e164 == numero_e164,
            WhatsAppUser.ativo.is_(True),
        )
        .options(selectinload(WhatsAppUser.user).selectinload(User.cliente))
    )
    return result.scalar_one_or_none()


async def _persistir(
    db: AsyncSession,
    *,
    direcao: DirecaoMensagem,
    numero_e164: str,
    user_id: UUID | None,
    texto: str,
    wuzapi_message_id: str | None = None,
    tools_usadas: list[dict[str, Any]] | None = None,
    tokens_prompt: int = 0,
    tokens_resposta: int = 0,
    duracao_ms: int = 0,
    erro: str | None = None,
) -> WhatsAppMensagem:
    msg = WhatsAppMensagem(
        direcao=direcao,
        numero_e164=numero_e164,
        user_id=user_id,
        texto=texto,
        wuzapi_message_id=wuzapi_message_id,
        tools_usadas=tools_usadas,
        tokens_prompt=tokens_prompt,
        tokens_resposta=tokens_resposta,
        duracao_ms=duracao_ms,
        erro=erro,
    )
    db.add(msg)
    await db.flush()
    return msg


# ============================================================
# Função pública (chamada pelo webhook)
# ============================================================


@dataclass(slots=True)
class ProcessamentoResultado:
    """O que o webhook precisa pra responder via Wuzapi."""

    deve_responder: bool
    texto_resposta: str | None
    motivo: str  # "ok", "numero_nao_autorizado", "duplicada", "erro"


async def processar_mensagem_inbound(
    db: AsyncSession,
    *,
    numero_e164: str,
    texto: str,
    wuzapi_message_id: str | None,
) -> ProcessamentoResultado:
    """Recebe mensagem do WhatsApp, gera resposta com Jarvis, persiste tudo.

    Retorna o que o webhook precisa pra enviar (ou ignorar) a resposta.
    """
    # Dedupe: se o mesmo message_id já foi processado, ignora
    if wuzapi_message_id:
        ja = await db.execute(
            select(WhatsAppMensagem.id).where(
                WhatsAppMensagem.wuzapi_message_id == wuzapi_message_id
            )
        )
        if ja.scalar_one_or_none():
            return ProcessamentoResultado(
                deve_responder=False, texto_resposta=None, motivo="duplicada"
            )

    wpp_user = await _resolver_usuario(db, numero_e164)

    if wpp_user is None:
        # Grava tentativa pra auditoria, mas NÃO responde
        await _persistir(
            db,
            direcao=DirecaoMensagem.INBOUND,
            numero_e164=numero_e164,
            user_id=None,
            texto=texto,
            wuzapi_message_id=wuzapi_message_id,
            erro="numero_nao_autorizado",
        )
        log.warning(
            "jarvis.numero_nao_autorizado",
            numero=numero_e164,
            chars=len(texto),
        )
        return ProcessamentoResultado(
            deve_responder=False,
            texto_resposta=None,
            motivo="numero_nao_autorizado",
        )

    user = wpp_user.user
    pode_aprovar = wpp_user.pode_aprovar_pagamento

    # Persiste inbound antes de processar (caso erro fatal)
    await _persistir(
        db,
        direcao=DirecaoMensagem.INBOUND,
        numero_e164=numero_e164,
        user_id=user.id,
        texto=texto,
        wuzapi_message_id=wuzapi_message_id,
    )

    historico = await _carregar_historico(
        db,
        numero_e164=numero_e164,
        horas=settings.JARVIS_HISTORICO_HORAS,
        limite=settings.JARVIS_HISTORICO_MAX,
    )
    # Remove a última mensagem se for igual à atual (acabou de ser persistida)
    if historico and historico[-1]["role"] == "user" and historico[-1]["content"] == texto:
        historico = historico[:-1]

    try:
        resultado = await _gerar_resposta(
            db,
            user=user,
            pode_aprovar=pode_aprovar,
            texto_usuario=texto,
            historico=historico,
        )
    except MedPagException as exc:
        await _persistir(
            db,
            direcao=DirecaoMensagem.OUTBOUND,
            numero_e164=numero_e164,
            user_id=user.id,
            texto=f"[ERRO] {exc.message}",
            erro=exc.message,
        )
        return ProcessamentoResultado(
            deve_responder=True,
            texto_resposta=(
                "Tive um problema técnico aqui ⚠️ "
                f"({exc.message}). Tenta de novo daqui a pouco."
            ),
            motivo="erro",
        )

    await _persistir(
        db,
        direcao=DirecaoMensagem.OUTBOUND,
        numero_e164=numero_e164,
        user_id=user.id,
        texto=resultado.texto_resposta,
        tools_usadas=resultado.tools_usadas,
        tokens_prompt=resultado.tokens_prompt,
        tokens_resposta=resultado.tokens_resposta,
        duracao_ms=resultado.duracao_ms,
    )

    return ProcessamentoResultado(
        deve_responder=True,
        texto_resposta=resultado.texto_resposta,
        motivo="ok",
    )


__all__ = [
    "GroqIndisponivelError",
    "JarvisFalhouError",
    "JarvisResultado",
    "ProcessamentoResultado",
    "processar_mensagem_inbound",
]
