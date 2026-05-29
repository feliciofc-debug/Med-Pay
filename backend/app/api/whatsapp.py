"""Rotas REST do módulo Jarvis.

- `POST /api/whatsapp/webhook`            → Wuzapi → Med-Pag (mensagens recebidas)
- `GET  /api/whatsapp/users`              → admin: lista whitelist
- `POST /api/whatsapp/users`              → admin: adiciona telefone
- `PUT  /api/whatsapp/users/{id}`         → admin: edita (ativar/desativar/aprovar)
- `DELETE /api/whatsapp/users/{id}`       → admin: remove
- `GET  /api/whatsapp/mensagens`          → admin: histórico (filtros)
- `GET  /api/whatsapp/instancia`          → admin: estado da sessão Wuzapi
- `POST /api/whatsapp/instancia/conectar` → admin: gera QR code
- `POST /api/whatsapp/instancia/desconectar` → admin: derruba sessão
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.deps import get_db, require_admin
from app.core.exceptions import (
    UsuarioNaoEncontradoError,
    ValidacaoError,
)
from app.models.user import User
from app.models.whatsapp import (
    DirecaoMensagem,
    StatusInstancia,
    WhatsAppInstancia,
    WhatsAppMensagem,
    WhatsAppUser,
)
from app.schemas.whatsapp import (
    AdotarInstanciaRequest,
    AtualizarWhatsAppUserRequest,
    CriarWhatsAppUserRequest,
    InstanciaOut,
    QRCodeOut,
    WhatsAppMensagemOut,
    WhatsAppUserOut,
    WuzapiWebhookEvent,
)
from app.services.jarvis_agent import processar_mensagem_inbound
from app.services.wuzapi_client import (
    WuzapiFalhouError,
    WuzapiIndisponivelError,
    wuzapi_client,
)

log = structlog.get_logger()
router = APIRouter()


# ============================================================
# Helpers
# ============================================================


_NUMERO_RE = re.compile(r"^\d{10,15}$")


def _normalizar_numero(raw: str) -> str:
    """E.164 sem +. Aceita formatos com +, hífen, parênteses, espaço."""
    s = re.sub(r"\D", "", raw or "")
    if not _NUMERO_RE.match(s):
        raise ValidacaoError(
            "Telefone inválido. Use o número completo com DDI+DDD, "
            "ex: 5521999998888."
        )
    return s


def _wpp_user_para_out(wpp: WhatsAppUser) -> WhatsAppUserOut:
    return WhatsAppUserOut.model_validate(
        {
            "id": wpp.id,
            "user_id": wpp.user_id,
            "user_nome": wpp.user.nome if wpp.user else "?",
            "user_email": wpp.user.email if wpp.user else "?",
            "user_role": wpp.user.role if wpp.user else "OPERADOR",
            "numero_e164": wpp.numero_e164,
            "apelido": wpp.apelido,
            "pode_aprovar_pagamento": wpp.pode_aprovar_pagamento,
            "ativo": wpp.ativo,
            "created_at": wpp.created_at,
        }
    )


# ============================================================
# Webhook (Wuzapi → Med-Pag)
# ============================================================


def _extrair_dados_mensagem(payload: dict[str, Any]) -> dict[str, str | None]:
    """Tenta extrair (numero, texto, message_id) do payload do Wuzapi.

    Wuzapi tem variações de schema entre versões. Testamos os caminhos
    mais comuns. Se nenhum bater, retorna campos None e o webhook
    devolve 200 (ack) sem processar.
    """
    info = payload.get("Info") or payload.get("info") or {}
    msg = payload.get("Message") or payload.get("message") or {}

    # numero (Chat = JID do remetente; Sender = quem mandou)
    chat = (
        info.get("Chat")
        or info.get("Sender")
        or info.get("RemoteJid")
        or info.get("From")
        or payload.get("From")
        or payload.get("from")
    )
    numero = None
    if isinstance(chat, str):
        # JID vem tipo "5521999998888@s.whatsapp.net"
        numero = chat.split("@")[0]
        numero = re.sub(r"\D", "", numero) or None

    # texto
    texto = (
        msg.get("conversation")
        or msg.get("Conversation")
        or msg.get("text")
        or msg.get("Text")
        or payload.get("body")
        or payload.get("Body")
    )
    if isinstance(texto, dict):
        texto = texto.get("text") or texto.get("Text")

    # message_id
    message_id = (
        info.get("Id") or info.get("ID") or info.get("MessageId") or payload.get("id")
    )

    # ignora mensagens que partiram do bot (FromMe=True)
    if info.get("IsFromMe") or info.get("FromMe") or msg.get("FromMe"):
        return {"numero": None, "texto": None, "message_id": None}

    return {
        "numero": numero if isinstance(numero, str) and numero else None,
        "texto": str(texto).strip() if texto else None,
        "message_id": str(message_id) if message_id else None,
    }


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def wuzapi_webhook(
    payload: WuzapiWebhookEvent,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
) -> dict[str, Any]:
    """Endpoint que o Wuzapi chama quando uma mensagem chega.

    Sempre retorna 200 (Wuzapi reenvia em caso de erro, e a gente
    quer evitar loop). Erros são logados e gravados no audit.
    """
    if settings.WUZAPI_WEBHOOK_SECRET:
        if x_webhook_secret != settings.WUZAPI_WEBHOOK_SECRET:
            log.warning(
                "whatsapp.webhook_secret_invalido",
                ip=request.client.host if request.client else None,
            )
            return {"ok": False, "motivo": "secret_invalido"}

    raw = payload.model_dump()
    evento = (raw.get("event") or "").lower()
    data = raw.get("data") or raw

    # Eventos que não são mensagem: ignoramos sem alarme (Connection, Receipt…)
    if evento and "message" not in evento:
        return {"ok": True, "motivo": "evento_ignorado", "evento": evento}

    extraido = _extrair_dados_mensagem(data if isinstance(data, dict) else raw)
    numero = extraido["numero"]
    texto = extraido["texto"]
    msg_id = extraido["message_id"]

    if not numero or not texto:
        return {"ok": True, "motivo": "payload_sem_dados"}

    # Processa via Jarvis
    try:
        resultado = await processar_mensagem_inbound(
            db,
            numero_e164=numero,
            texto=texto,
            wuzapi_message_id=msg_id,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("whatsapp.webhook_erro", numero=numero)
        return {"ok": False, "motivo": "erro_interno", "erro": str(exc)}

    # Envia resposta via Wuzapi
    if resultado.deve_responder and resultado.texto_resposta:
        try:
            await _enviar_resposta_via_wuzapi(
                db, numero=numero, texto=resultado.texto_resposta
            )
        except (WuzapiIndisponivelError, WuzapiFalhouError) as exc:
            log.error("whatsapp.envio_falhou", numero=numero, erro=exc.message)
            return {
                "ok": False,
                "motivo": "envio_falhou",
                "erro": exc.message,
            }

    return {"ok": True, "motivo": resultado.motivo}


async def _enviar_resposta_via_wuzapi(
    db: AsyncSession, *, numero: str, texto: str
) -> None:
    """Envia mensagem usando o token da instância configurada."""
    instancia = await _instancia_ativa(db)
    if instancia is None or instancia.status != StatusInstancia.CONECTADA:
        # Sem instância conectada não tem como enviar
        log.warning("whatsapp.sem_instancia_conectada")
        return
    await wuzapi_client.enviar_texto(
        instancia.wuzapi_token, numero_e164=numero, texto=texto
    )


# ============================================================
# Whitelist (CRUD)
# ============================================================


@router.get("/users", response_model=list[WhatsAppUserOut])
async def listar_users(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[WhatsAppUserOut]:
    result = await db.execute(
        select(WhatsAppUser)
        .options(selectinload(WhatsAppUser.user))
        .order_by(WhatsAppUser.created_at.desc())
    )
    return [_wpp_user_para_out(u) for u in result.scalars().all()]


@router.post(
    "/users",
    response_model=WhatsAppUserOut,
    status_code=status.HTTP_201_CREATED,
)
async def criar_user(
    payload: CriarWhatsAppUserRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> WhatsAppUserOut:
    numero = _normalizar_numero(payload.numero_e164)

    # Confere que user existe
    user_q = await db.execute(select(User).where(User.id == payload.user_id))
    user_obj = user_q.scalar_one_or_none()
    if user_obj is None:
        raise UsuarioNaoEncontradoError(
            f"Usuário {payload.user_id} não encontrado"
        )

    # Idempotência: se já existe, atualiza vínculo
    existente_q = await db.execute(
        select(WhatsAppUser).where(WhatsAppUser.numero_e164 == numero)
    )
    existente = existente_q.scalar_one_or_none()
    if existente is not None:
        existente.user_id = payload.user_id
        existente.apelido = payload.apelido
        existente.pode_aprovar_pagamento = payload.pode_aprovar_pagamento
        existente.ativo = True
        await db.flush()
        result = await db.execute(
            select(WhatsAppUser)
            .where(WhatsAppUser.id == existente.id)
            .options(selectinload(WhatsAppUser.user))
        )
        return _wpp_user_para_out(result.scalar_one())

    novo = WhatsAppUser(
        user_id=payload.user_id,
        numero_e164=numero,
        apelido=payload.apelido,
        pode_aprovar_pagamento=payload.pode_aprovar_pagamento,
        ativo=True,
    )
    db.add(novo)
    await db.flush()
    result = await db.execute(
        select(WhatsAppUser)
        .where(WhatsAppUser.id == novo.id)
        .options(selectinload(WhatsAppUser.user))
    )
    return _wpp_user_para_out(result.scalar_one())


@router.put("/users/{wpp_user_id}", response_model=WhatsAppUserOut)
async def atualizar_user(
    wpp_user_id: UUID,
    payload: AtualizarWhatsAppUserRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> WhatsAppUserOut:
    result = await db.execute(
        select(WhatsAppUser)
        .where(WhatsAppUser.id == wpp_user_id)
        .options(selectinload(WhatsAppUser.user))
    )
    wpp = result.scalar_one_or_none()
    if wpp is None:
        raise UsuarioNaoEncontradoError("Vínculo WhatsApp não encontrado")

    if payload.apelido is not None:
        wpp.apelido = payload.apelido
    if payload.pode_aprovar_pagamento is not None:
        wpp.pode_aprovar_pagamento = payload.pode_aprovar_pagamento
    if payload.ativo is not None:
        wpp.ativo = payload.ativo

    await db.flush()
    return _wpp_user_para_out(wpp)


@router.delete(
    "/users/{wpp_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def deletar_user(
    wpp_user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Response:
    result = await db.execute(
        select(WhatsAppUser).where(WhatsAppUser.id == wpp_user_id)
    )
    wpp = result.scalar_one_or_none()
    if wpp is None:
        raise UsuarioNaoEncontradoError("Vínculo WhatsApp não encontrado")
    await db.delete(wpp)
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============================================================
# Histórico de mensagens
# ============================================================


@router.get("/mensagens", response_model=list[WhatsAppMensagemOut])
async def listar_mensagens(
    numero_e164: str | None = Query(None),
    direcao: DirecaoMensagem | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[WhatsAppMensagemOut]:
    query = (
        select(WhatsAppMensagem)
        .order_by(desc(WhatsAppMensagem.created_at))
        .limit(limit)
        .offset(offset)
    )
    if numero_e164:
        query = query.where(WhatsAppMensagem.numero_e164 == _normalizar_numero(numero_e164))
    if direcao is not None:
        query = query.where(WhatsAppMensagem.direcao == direcao)

    result = await db.execute(query)
    return [WhatsAppMensagemOut.model_validate(m) for m in result.scalars().all()]


# ============================================================
# Instância Wuzapi
# ============================================================


async def _instancia_ativa(db: AsyncSession) -> WhatsAppInstancia | None:
    result = await db.execute(
        select(WhatsAppInstancia)
        .where(WhatsAppInstancia.ativa.is_(True))
        .order_by(desc(WhatsAppInstancia.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/instancia", response_model=InstanciaOut | None)
async def obter_instancia(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> InstanciaOut | None:
    inst = await _instancia_ativa(db)
    if inst is None:
        return None

    # Sincroniza status com Wuzapi (best-effort, NUNCA quebra o endpoint).
    # O client ja normaliza o payload aninhado {data: {...}}.
    if wuzapi_client.is_configured():
        try:
            data = await wuzapi_client.status(inst.wuzapi_token)
            conectado = bool(
                data.get("loggedIn")
                or data.get("LoggedIn")
                or data.get("connected")
                or data.get("Connected")
            )
            inst.status = (
                StatusInstancia.CONECTADA if conectado else StatusInstancia.DESCONECTADA
            )
            # Se ja tem JID (telefone pareado), atualiza numero_bot
            jid = data.get("jid") or data.get("Jid")
            if isinstance(jid, str) and ":" in jid and not inst.numero_bot:
                numero_extraido = jid.split(":")[0]
                # Guard contra valor muito longo (campo e VARCHAR(20))
                if len(numero_extraido) <= 20:
                    inst.numero_bot = numero_extraido
            try:
                await db.flush()
            except Exception as flush_exc:  # noqa: BLE001
                log.warning(
                    "whatsapp.flush_falhou", erro=str(flush_exc)
                )
                await db.rollback()
        except Exception as exc:  # noqa: BLE001
            # Qualquer erro no Wuzapi (timeout, rede, schema, etc) NUNCA
            # pode quebrar este endpoint. So loga.
            log.warning(
                "whatsapp.sync_status_falhou",
                erro=str(exc),
                tipo=type(exc).__name__,
            )

    return InstanciaOut.model_validate(inst)


@router.post("/instancia/conectar", response_model=QRCodeOut)
async def conectar_instancia(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> QRCodeOut:
    """Conecta uma sessao WhatsApp e devolve o QR code.

    Fluxo simplificado (replica o que a AMZ Ofertas faz e funciona):

    1. Resolve a instancia a usar:
        a. Se ja existe WhatsAppInstancia ativa no DB → usa essa
        b. Senao, se WUZAPI_INSTANCE_TOKEN esta configurado → cria
           registro local apontando pra essa sessao fixa (caminho recomendado)
        c. Senao, tenta criar via /admin/users (fallback)
    2. Chama obter_qr() que sozinho cuida de:
        - GET /session/status (as vezes ja vem QR)
        - GET /session/qr
        - POST /session/connect + retry no /session/qr
        (mesmo padrao do amzofertas-independent que funciona em prod)
    3. Configura webhook (best-effort, nao bloqueia se falhar)
    4. Retorna o QR code (ou null se ja conectado)
    """
    if not wuzapi_client.is_configured():
        raise WuzapiIndisponivelError(
            "WUZAPI_URL precisa estar configurada. Adicione no Render."
        )

    # 1. Resolve a instancia
    inst = await _instancia_ativa(db)
    if inst is None:
        # Estrategia recomendada: usar uma sessao fixa configurada por env
        token_fixo = settings.WUZAPI_INSTANCE_TOKEN
        if token_fixo:
            instance_id = (
                settings.WUZAPI_INSTANCE_ID or "medpag-jarvis"
            )
            inst = WhatsAppInstancia(
                wuzapi_instance_id=instance_id,
                wuzapi_token=token_fixo,
                status=StatusInstancia.AGUARDANDO_QR,
                ativa=True,
            )
            db.add(inst)
            await db.flush()
            log.info(
                "whatsapp.instancia_criada_via_env",
                instance_id=instance_id,
            )
        elif settings.WUZAPI_ADMIN_TOKEN:
            # Fallback: cria via admin/users (depende do schema do fork)
            try:
                wuz = await wuzapi_client.criar_instancia("medpag-jarvis")
                inst = WhatsAppInstancia(
                    wuzapi_instance_id=wuz.instance_id,
                    wuzapi_token=wuz.token,
                    status=StatusInstancia.AGUARDANDO_QR,
                    ativa=True,
                )
                db.add(inst)
                await db.flush()
            except (WuzapiIndisponivelError, WuzapiFalhouError) as exc:
                raise WuzapiFalhouError(
                    f"Nao foi possivel criar a sessao no Wuzapi: {exc.message}. "
                    "Configure WUZAPI_INSTANCE_TOKEN nas env vars do Render "
                    "apontando pra um user ja criado no servidor."
                ) from exc
        else:
            raise WuzapiIndisponivelError(
                "Configure WUZAPI_INSTANCE_TOKEN no Render apontando pra "
                "um user/sessao ja criada no servidor Wuzapi. Esse e o "
                "jeito recomendado."
            )

    # 2. Tenta obter QR (a logica de fluxo esta no client)
    # Erros de connect/qr nao quebram aqui: o obter_qr retorna None se ja
    # esta conectado, e tambem retorna None se algo deu erro nas chamadas
    # internas (logs no client).
    qr = await wuzapi_client.obter_qr(inst.wuzapi_token)

    # 3. Configura webhook (best-effort, nao falha o request)
    if qr is None:
        # Ja conectado — sincroniza numero_bot
        try:
            st = await wuzapi_client.status(inst.wuzapi_token)
            jid = st.get("jid") or st.get("Jid")
            if isinstance(jid, str) and ":" in jid and not inst.numero_bot:
                inst.numero_bot = jid.split(":")[0]
        except (WuzapiIndisponivelError, WuzapiFalhouError):
            pass

    try:
        webhook_url = str(request.url_for("wuzapi_webhook"))
        await wuzapi_client.configurar_webhook(
            inst.wuzapi_token, url=webhook_url
        )
    except (WuzapiIndisponivelError, WuzapiFalhouError) as exc:
        log.warning("whatsapp.webhook_setup_falhou", erro=exc.message)

    # 4. Atualiza estado e retorna
    inst.status = (
        StatusInstancia.CONECTADA if qr is None else StatusInstancia.AGUARDANDO_QR
    )
    inst.ultimo_qr_base64 = qr
    if qr is not None:
        from datetime import UTC, datetime as _dt
        inst.ultimo_qr_at = _dt.now(UTC)
    await db.flush()

    return QRCodeOut(qr_base64=qr, status=inst.status)


@router.post("/instancia/desconectar", status_code=status.HTTP_200_OK)
async def desconectar_instancia(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict[str, str]:
    inst = await _instancia_ativa(db)
    if inst is None:
        return {"status": "sem_instancia"}
    if wuzapi_client.is_configured():
        try:
            await wuzapi_client.desconectar(inst.wuzapi_token)
        except (WuzapiIndisponivelError, WuzapiFalhouError):
            pass
    inst.status = StatusInstancia.DESCONECTADA
    await db.flush()
    return {"status": "desconectada"}


@router.get("/instancia/diagnostico")
async def diagnostico_wuzapi(
    _admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """Diagnostico do servidor Wuzapi: lista users disponiveis com status.

    Util para:
    - Ver o que ja existe na VPS sem precisar de SSH
    - Decidir qual sessao adotar via "Adotar instancia existente"
    - Confirmar que admin token + header estao funcionando

    Resposta:
    {
        "wuzapi_url": "http://...",
        "ok": true,
        "users": [
            {
                "name": "jarvis",
                "id": "...",
                "token_preview": "jarvis-byc...",
                "loggedIn": true,
                "jid": "5521...@s.whatsapp.net",
                "webhook": "https://...",
            },
            ...
        ],
        "raw": {...}  # so primeiros 1000 chars em modo debug
    }
    """
    if not wuzapi_client.is_configured():
        return {
            "wuzapi_url": None,
            "ok": False,
            "erro": (
                "WUZAPI_URL ou WUZAPI_ADMIN_TOKEN nao configurados. "
                "Verifique as variaveis de ambiente no Render."
            ),
            "users": [],
        }

    try:
        users = await wuzapi_client.listar_instancias()
    except (WuzapiIndisponivelError, WuzapiFalhouError) as exc:
        return {
            "wuzapi_url": wuzapi_client.base_url,
            "ok": False,
            "erro": exc.message,
            "users": [],
        }

    # Normaliza cada user pra UI conseguir mostrar bonito
    resultado: list[dict[str, Any]] = []
    for u in users:
        token = u.get("token") or u.get("Token") or u.get("apiToken") or ""
        nome = u.get("name") or u.get("Name") or u.get("username") or ""
        instance_id = (
            u.get("id") or u.get("ID") or u.get("userid") or nome or ""
        )
        jid = u.get("jid") or u.get("JID") or None
        connected = u.get("connected") if u.get("connected") is not None else u.get("Connected")
        logged_in = u.get("loggedIn") if u.get("loggedIn") is not None else u.get("LoggedIn")
        webhook = u.get("webhook") or u.get("Webhook") or None

        resultado.append(
            {
                "name": nome,
                "id": str(instance_id) if instance_id else "",
                "token": token,
                "token_preview": (
                    f"{token[:12]}..." if token and len(token) > 14 else token
                ),
                "jid": jid,
                "numero": (
                    jid.split(":")[0]
                    if isinstance(jid, str) and ":" in jid
                    else None
                ),
                "connected": connected,
                "loggedIn": logged_in,
                "webhook": webhook,
            }
        )

    return {
        "wuzapi_url": wuzapi_client.base_url,
        "ok": True,
        "total": len(resultado),
        "users": resultado,
    }


@router.post("/instancia/adotar", response_model=InstanciaOut)
async def adotar_instancia(
    payload: AdotarInstanciaRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> InstanciaOut:
    """Adota uma instancia Wuzapi ja existente (criada manualmente na VPS).

    Fluxo:
    1. Admin gera o QR code direto no Wuzapi (via curl/UI) usando um user
       ja criado la (ex: 'jarvis' com token 'jarvis-byceo-2026')
    2. Escaneia o QR com o celular do bot
    3. Cola aqui o instance_id + token + (opcional) numero
    4. Med-Pay passa a usar essa instancia pra enviar/receber

    Util quando:
    - O fork do Wuzapi tem schema diferente que confunde o criar_instancia
    - Voce ja tem instancias prontas e quer reaproveitar
    - Quer controle total sobre qual sessao Wuzapi o Med-Pay usa
    """
    instance_id = payload.wuzapi_instance_id.strip()
    token = payload.wuzapi_token.strip()
    numero = (payload.numero_bot or "").strip() or None

    if not instance_id or not token:
        raise ValidacaoError(
            "instance_id e token sao obrigatorios"
        )

    # Valida que o token funciona contra o Wuzapi (best-effort)
    # Tambem captura o numero do bot se a sessao ja estiver pareada.
    numero_detectado: str | None = None
    if wuzapi_client.is_configured():
        try:
            data = await wuzapi_client.status(token)
            conectado = bool(
                data.get("loggedIn")
                or data.get("LoggedIn")
                or data.get("connected")
                or data.get("Connected")
            )
            status_inicial = (
                StatusInstancia.CONECTADA
                if conectado
                else StatusInstancia.AGUARDANDO_QR
            )
            jid = data.get("jid") or data.get("Jid")
            if isinstance(jid, str) and ":" in jid:
                numero_detectado = jid.split(":")[0]
        except (WuzapiIndisponivelError, WuzapiFalhouError) as exc:
            raise ValidacaoError(
                f"Token nao reconhecido pelo servidor Wuzapi: {exc.message}. "
                "Confira se voce copiou o token correto do user no Wuzapi."
            ) from exc
    else:
        status_inicial = StatusInstancia.DESCONECTADA

    # Desativa instancia ativa antiga (so pode ter uma ativa)
    atual = await _instancia_ativa(db)
    if atual is not None:
        atual.ativa = False
        await db.flush()

    # Verifica se ja existe registro com esse wuzapi_instance_id
    existente_q = await db.execute(
        select(WhatsAppInstancia).where(
            WhatsAppInstancia.wuzapi_instance_id == instance_id
        )
    )
    inst = existente_q.scalar_one_or_none()
    numero_final = numero or numero_detectado
    if inst is not None:
        inst.wuzapi_token = token
        inst.ativa = True
        inst.status = status_inicial
        if numero_final:
            inst.numero_bot = numero_final
    else:
        inst = WhatsAppInstancia(
            wuzapi_instance_id=instance_id,
            wuzapi_token=token,
            numero_bot=numero_final,
            status=status_inicial,
            ativa=True,
        )
        db.add(inst)
    await db.flush()

    log.info(
        "whatsapp.instancia_adotada",
        instance_id=instance_id,
        status=status_inicial.value,
        admin_user=_admin.email,
    )

    return InstanciaOut.model_validate(inst)
