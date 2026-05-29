"""Cliente HTTP do Wuzapi (servidor WhatsApp não-oficial).

Wuzapi expõe uma API RESTful pra:
    - criar/listar instâncias (sessões WhatsApp)
    - obter QR code de pareamento
    - enviar mensagem texto
    - enviar mídia (imagem, doc) — não usado no MVP do Jarvis
    - configurar webhook (URL + eventos)

Documentação: https://github.com/asternic/wuzapi

Segurança:
    - O token admin manda em ações administrativas (criar instância,
      configurar webhook, etc.).
    - O token da instância manda em ações da própria instância
      (enviar mensagem). Esse token é gerado pelo Wuzapi quando a
      instância é criada e fica salvo em `WhatsAppInstancia.wuzapi_token`.

Falhas:
    - Wuzapi fora do ar / token inválido → `WuzapiIndisponivelError`
    - Resposta de erro do Wuzapi → `WuzapiFalhouError` com detalhes
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from app.core.config import settings
from app.core.exceptions import MedPagException

log = structlog.get_logger()

HTTP_TIMEOUT_SECONDS = 30


class WuzapiIndisponivelError(MedPagException):
    code = "WUZAPI_INDISPONIVEL"
    status_code = 503


class WuzapiFalhouError(MedPagException):
    code = "WUZAPI_FALHOU"
    status_code = 502


@dataclass(frozen=True, slots=True)
class WuzapiInstance:
    instance_id: str
    token: str


class WuzapiClient:
    """Cliente do servidor Wuzapi.

    Use a instância singleton `wuzapi_client` em service code.
    """

    def __init__(self) -> None:
        self.base_url: str | None = (settings.WUZAPI_URL or "").rstrip("/") or None
        self.admin_token: str | None = settings.WUZAPI_ADMIN_TOKEN
        # Configurável: Wuzapi oficial usa "Token", forks tipo AMZ usam
        # "Authorization". Default = "Token" pra manter compatibilidade.
        self.auth_header: str = (settings.WUZAPI_AUTH_HEADER or "Token").strip() or "Token"

    def is_configured(self) -> bool:
        return bool(self.base_url and self.admin_token)

    # ============================================================
    # Helpers HTTP
    # ============================================================

    async def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.base_url:
            raise WuzapiIndisponivelError(
                "WUZAPI_URL não configurada. Configure no .env do backend."
            )
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}
        # Nome do header é configurável via WUZAPI_AUTH_HEADER porque
        # forks como o da AMZ Ofertas usam "Authorization" em vez de "Token".
        if token:
            headers[self.auth_header] = token

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
                resp = await client.request(
                    method, url, headers=headers, json=json, params=params
                )
        except httpx.HTTPError as exc:
            log.error("wuzapi.connect_error", url=url, erro=str(exc))
            raise WuzapiIndisponivelError(
                f"Falha ao conectar no Wuzapi: {exc}"
            ) from exc

        if resp.status_code in (401, 403):
            raise WuzapiIndisponivelError(
                f"Token Wuzapi inválido ({resp.status_code} no header "
                f"'{self.auth_header}'). Verifique WUZAPI_ADMIN_TOKEN e "
                "WUZAPI_AUTH_HEADER (Token=oficial, Authorization=fork AMZ)."
            )

        if resp.status_code >= 400:
            log.error(
                "wuzapi.http_error",
                status=resp.status_code,
                body=resp.text[:500],
                url=url,
            )
            raise WuzapiFalhouError(
                f"Wuzapi respondeu HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            return resp.json() if resp.content else {}
        except ValueError as exc:
            raise WuzapiFalhouError(
                f"Wuzapi devolveu payload inválido: {exc}"
            ) from exc

    # ============================================================
    # Operações administrativas (precisam admin token)
    # ============================================================

    async def listar_instancias(self) -> list[dict[str, Any]]:
        """Lista as instâncias (sessões) cadastradas no Wuzapi."""
        data = await self._request(
            "GET", "/admin/users", token=self.admin_token
        )
        if isinstance(data, dict):
            users = data.get("data") or data.get("users") or data.get("Users") or []
        else:
            users = data
        return [u for u in users if isinstance(u, dict)]

    async def criar_instancia(self, nome: str) -> WuzapiInstance:
        """Cria uma instância (sessão WhatsApp) no Wuzapi.

        Se já existir um user com o mesmo nome, REUSA — não cria duplicado.
        Útil quando o Med-Pay reinicia e a instância da VPS persiste.

        Forks do Wuzapi (ex: AMZ Ofertas) podem retornar HTTP 409
        "user with this token already exists" quando duas chamadas batem
        no mesmo nome. Aqui interceptamos esse caso e fazemos lookup.
        """
        # Primeiro tenta achar uma instância existente com esse nome
        try:
            existentes = await self.listar_instancias()
            for u in existentes:
                if (u.get("name") or u.get("Name") or "") == nome:
                    instance_id = str(u.get("id") or u.get("Id") or nome)
                    token = str(u.get("token") or u.get("Token") or "")
                    if token:
                        log.info(
                            "wuzapi.instancia_reusada", nome=nome, id=instance_id
                        )
                        return WuzapiInstance(
                            instance_id=instance_id, token=token
                        )
        except (WuzapiIndisponivelError, WuzapiFalhouError):
            # Se o listar falhou, segue tentando criar (pode dar 409)
            pass

        payload = {"name": nome}
        try:
            data = await self._request(
                "POST", "/admin/users", token=self.admin_token, json=payload
            )
        except WuzapiFalhouError as exc:
            # 409 conflict → tenta carregar de novo, agora exigindo achar
            if "409" in str(exc) or "already exists" in str(exc).lower():
                existentes = await self.listar_instancias()
                for u in existentes:
                    if (u.get("name") or u.get("Name") or "") == nome:
                        instance_id = str(u.get("id") or u.get("Id") or nome)
                        token = str(u.get("token") or u.get("Token") or "")
                        if token:
                            log.info(
                                "wuzapi.instancia_recuperada_apos_409",
                                nome=nome,
                                id=instance_id,
                            )
                            return WuzapiInstance(
                                instance_id=instance_id, token=token
                            )
                raise WuzapiFalhouError(
                    f"Wuzapi disse que '{nome}' já existe mas não conseguimos "
                    "encontrar o registro. Verifique manualmente no servidor."
                ) from exc
            raise

        instance_id = str(data.get("id") or data.get("Id") or nome)
        token = str(data.get("token") or data.get("Token") or "")
        if not token:
            raise WuzapiFalhouError(
                "Wuzapi criou instância sem token na resposta"
            )
        return WuzapiInstance(instance_id=instance_id, token=token)

    # ============================================================
    # Operações da instância (precisam token da instância)
    # ============================================================

    async def conectar(
        self, instance_token: str, *, webhook_url: str | None = None
    ) -> dict[str, Any]:
        """Inicia conexão WhatsApp.

        Após chamar, deve-se chamar `obter_qr` em loop até pareamento.
        """
        payload: dict[str, Any] = {}
        if webhook_url:
            payload["Webhook"] = webhook_url
            payload["Events"] = ["Message"]
        return await self._request(
            "POST", "/session/connect", token=instance_token, json=payload
        )

    async def desconectar(self, instance_token: str) -> dict[str, Any]:
        return await self._request(
            "POST", "/session/disconnect", token=instance_token
        )

    async def status(self, instance_token: str) -> dict[str, Any]:
        return await self._request(
            "GET", "/session/status", token=instance_token
        )

    async def obter_qr(self, instance_token: str) -> str | None:
        """Devolve QR code base64 (data URI) para parear o WhatsApp.

        Retorna None quando já está conectado.
        """
        try:
            data = await self._request(
                "GET", "/session/qr", token=instance_token
            )
        except WuzapiFalhouError:
            return None
        qr = data.get("data") if isinstance(data, dict) else None
        if not qr and isinstance(data, dict):
            qr = data.get("QRCode") or data.get("qrcode")
        return str(qr) if qr else None

    async def configurar_webhook(
        self,
        instance_token: str,
        *,
        url: str,
        eventos: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "webhook": url,
            "events": eventos or ["Message"],
        }
        return await self._request(
            "POST", "/webhook", token=instance_token, json=payload
        )

    async def enviar_texto(
        self,
        instance_token: str,
        *,
        numero_e164: str,
        texto: str,
    ) -> dict[str, Any]:
        """Envia uma mensagem de texto.

        `numero_e164` deve ser o número COMPLETO sem `+`, ex:
        `5521999998888`.
        """
        payload = {
            "Phone": numero_e164,
            "Body": texto,
        }
        return await self._request(
            "POST",
            "/chat/send/text",
            token=instance_token,
            json=payload,
        )


# Singleton
wuzapi_client = WuzapiClient()


__all__ = [
    "WuzapiClient",
    "WuzapiFalhouError",
    "WuzapiIndisponivelError",
    "WuzapiInstance",
    "wuzapi_client",
]
