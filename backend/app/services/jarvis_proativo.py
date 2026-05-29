"""Jarvis proativo — envia mensagens sem esperar o usuário falar.

Casos de uso:

- **Relatório diário** (8h Brasília): para cada usuário que ligou
  `receber_relatorio_diario=True`, monta um diagnóstico + problemas e
  envia via WhatsApp.
- **Alertas pontuais** (futuro): lote travado por X horas, taxa de
  devolução acima do baseline, trial vencendo, etc.

O envio passa pelo Wuzapi (mesma instância configurada). Tudo persiste
em `WhatsAppMensagem` (direcao=OUTBOUND) pra ficar auditável.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.whatsapp import (
    DirecaoMensagem,
    StatusInstancia,
    WhatsAppInstancia,
    WhatsAppMensagem,
    WhatsAppUser,
)
from app.services.jarvis_tools import (
    diagnostico_plataforma,
    identificar_problemas,
    pipeline_comercial,
)
from app.services.wuzapi_client import (
    WuzapiFalhouError,
    WuzapiIndisponivelError,
    wuzapi_client,
)

log = structlog.get_logger()


# ============================================================
# Composição de mensagens (sem LLM — texto determinístico,
# barato, não corre risco de alucinar números)
# ============================================================


def _compor_relatorio_diario(
    nome: str,
    *,
    diagnostico: dict,
    problemas: dict,
    pipeline: dict | None = None,
) -> str:
    """Texto curto, formato de mensagem de WhatsApp matinal.

    Determinístico de propósito — Felício acordando não quer LLM caro
    e nem chance de alucinar. Se faltar dado, omite a linha.
    """
    saudacao = "Bom dia"
    if datetime.now(UTC).weekday() == 0:
        saudacao = "Bom dia, semana nova"

    linhas = [f"☀️ {saudacao}, {nome.split()[0]}!"]
    linhas.append("")

    # Saúde geral
    saude = diagnostico.get("saude_geral", "ok")
    if saude == "ok":
        linhas.append("✅ Tudo rodando bem por aqui.")
    elif saude == "alerta":
        linhas.append("⚠️ Plataforma em ALERTA — vale dar uma olhada.")
    else:
        linhas.append("🚨 Plataforma em estado CRÍTICO — atenção urgente.")

    flags = diagnostico.get("alertas") or []
    if flags:
        linhas.append("")
        linhas.append("*Pontos do dia:*")
        for f in flags[:5]:
            linhas.append(f"- {f}")

    # Problemas críticos
    crits = [
        p for p in (problemas.get("problemas") or [])
        if p.get("severidade") == "critico"
    ]
    if crits:
        linhas.append("")
        linhas.append("*🚨 Itens críticos:*")
        for p in crits[:3]:
            linhas.append(f"- {p.get('descricao', '?')}")
            acao = p.get("acao_sugerida")
            if acao:
                linhas.append(f"  → {acao}")

    # Pipeline (só pra MedPag interno)
    if pipeline:
        mrr = pipeline.get("mrr_estimado_reais", 0)
        trials = pipeline.get("trials_vencendo_7d") or []
        linhas.append("")
        linhas.append(
            f"💼 *MRR atual:* R$ {mrr:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        if trials:
            linhas.append(f"⏳ {len(trials)} trial(s) vencendo em 7 dias.")

    linhas.append("")
    linhas.append("Manda mensagem se quiser detalhar qualquer um desses.")
    return "\n".join(linhas)


# ============================================================
# Envio + persistência
# ============================================================


async def _instancia_conectada(
    db: AsyncSession,
) -> WhatsAppInstancia | None:
    result = await db.execute(
        select(WhatsAppInstancia)
        .where(
            WhatsAppInstancia.ativa.is_(True),
            WhatsAppInstancia.status == StatusInstancia.CONECTADA,
        )
        .order_by(desc(WhatsAppInstancia.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def enviar_mensagem_proativa(
    db: AsyncSession,
    *,
    numero_e164: str,
    texto: str,
    user_id: UUID | None,
) -> bool:
    """Envia uma mensagem do Jarvis sem que o usuário tenha provocado.

    Retorna True se enviou, False se falhou (sem instância, Wuzapi off, etc).
    """
    inst = await _instancia_conectada(db)
    if inst is None:
        log.warning("jarvis.proativo.sem_instancia", numero=numero_e164)
        return False
    try:
        await wuzapi_client.enviar_texto(
            inst.wuzapi_token, numero_e164=numero_e164, texto=texto
        )
    except (WuzapiIndisponivelError, WuzapiFalhouError) as exc:
        log.error(
            "jarvis.proativo.envio_falhou",
            numero=numero_e164,
            erro=exc.message,
        )
        return False

    msg = WhatsAppMensagem(
        direcao=DirecaoMensagem.OUTBOUND,
        numero_e164=numero_e164,
        user_id=user_id,
        texto=texto,
    )
    db.add(msg)
    await db.flush()
    return True


# ============================================================
# Job de relatório diário (chamado pelo Celery beat às 8h SP)
# ============================================================


async def rodar_relatorio_diario(db: AsyncSession) -> dict[str, int]:
    """Para cada WhatsAppUser com `receber_relatorio_diario=True`,
    monta diagnóstico e envia. Retorna contadores.
    """
    result = await db.execute(
        select(WhatsAppUser)
        .where(
            WhatsAppUser.ativo.is_(True),
            WhatsAppUser.receber_relatorio_diario.is_(True),
        )
        .options(selectinload(WhatsAppUser.user).selectinload(User.cliente))
    )
    inscritos = list(result.scalars().all())

    if not inscritos:
        log.info("jarvis.proativo.sem_inscritos")
        return {"inscritos": 0, "enviados": 0, "falhas": 0}

    enviados = 0
    falhas = 0

    for wpp_user in inscritos:
        user = wpp_user.user
        try:
            diag = await diagnostico_plataforma(db, user)
            probs = await identificar_problemas(db, user)
            pipe = None
            # Pipeline só faz sentido pra ADMIN MedPag interno
            if user.cliente_id is None:
                pipe = await pipeline_comercial(db, user)
            texto = _compor_relatorio_diario(
                user.nome,
                diagnostico=diag,
                problemas=probs,
                pipeline=pipe,
            )
            ok = await enviar_mensagem_proativa(
                db,
                numero_e164=wpp_user.numero_e164,
                texto=texto,
                user_id=user.id,
            )
            if ok:
                enviados += 1
            else:
                falhas += 1
        except Exception:  # noqa: BLE001
            log.exception(
                "jarvis.proativo.usuario_falhou",
                user_id=str(user.id),
            )
            falhas += 1

    log.info(
        "jarvis.proativo.relatorio_diario",
        inscritos=len(inscritos),
        enviados=enviados,
        falhas=falhas,
    )
    return {
        "inscritos": len(inscritos),
        "enviados": enviados,
        "falhas": falhas,
    }


__all__ = [
    "enviar_mensagem_proativa",
    "rodar_relatorio_diario",
]
