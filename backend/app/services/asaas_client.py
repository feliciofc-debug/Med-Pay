"""Cliente HTTP fino pra API do Asaas.

Asaas é o gateway brasileiro que a gente escolheu pra cobrança
recorrente das assinaturas MedPag. Razões:
    - PIX, boleto e cartão com taxas locais
    - Sandbox livre (sandbox.asaas.com) com chave de teste
    - Webhook robusto pra atualizar status sozinho

Configuração:
    ASAAS_API_KEY      - chave do token "access_token" do Asaas
    ASAAS_BASE_URL     - https://sandbox.asaas.com/api/v3 (sandbox)
                         https://api.asaas.com/api/v3    (prod)

Filosofia:
    Cliente puro, sem regra de negócio. Funções retornam o JSON do
    Asaas direto. Quem traduz pra Cliente.asaas_* é o `asaas_service`.

Sem chave configurada: `is_configured()` → False, chamadas levantam
`AsaasIndisponivelError` (503). Frontend mostra banner pedindo setup.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.core.config import settings
from app.core.exceptions import MedPagException

log = structlog.get_logger()


# ============================================================
# Exceções
# ============================================================


class AsaasIndisponivelError(MedPagException):
    code = "ASAAS_INDISPONIVEL"
    status_code = 503


class AsaasFalhouError(MedPagException):
    code = "ASAAS_FALHOU"
    status_code = 502


# ============================================================
# Cliente
# ============================================================


class AsaasClient:
    """Wrapper minimal pra endpoints do Asaas que a gente usa."""

    TIMEOUT_S = 20.0

    def __init__(self) -> None:
        self._api_key = settings.ASAAS_API_KEY
        self._base_url = settings.ASAAS_BASE_URL.rstrip("/")

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "access_token": self._api_key or "",
            "Content-Type": "application/json",
            "User-Agent": "MedPag/0.1",
        }

    async def _request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise AsaasIndisponivelError(
                "ASAAS_API_KEY não configurada. "
                "Defina no .env pra habilitar cobrança."
            )

        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_S) as client:
                resp = await client.request(
                    method, url, headers=self._headers(), json=json
                )
        except httpx.HTTPError as exc:
            log.exception("asaas.network_error", path=path)
            raise AsaasIndisponivelError(
                f"Falha de rede ao falar com Asaas: {exc}"
            ) from exc

        if resp.status_code >= 500:
            log.error(
                "asaas.server_error",
                status=resp.status_code,
                path=path,
                body=resp.text[:500],
            )
            raise AsaasIndisponivelError(
                f"Asaas devolveu {resp.status_code}: {resp.text[:200]}"
            )

        # Erros 4xx — Asaas devolve {"errors": [{"code": "...", "description": "..."}]}
        if resp.status_code >= 400:
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}
            log.warning(
                "asaas.client_error",
                status=resp.status_code,
                path=path,
                data=data,
            )
            raise AsaasFalhouError(_extrair_mensagem_erro(data))

        try:
            return resp.json()  # type: ignore[no-any-return]
        except Exception as exc:  # noqa: BLE001
            raise AsaasFalhouError(
                f"Resposta não-JSON do Asaas: {resp.text[:200]}"
            ) from exc

    # =================================================
    # Customers (clientes do Asaas)
    # =================================================

    async def criar_customer(
        self,
        *,
        nome: str,
        cpf_cnpj: str | None,
        email: str | None,
        telefone: str | None = None,
        external_reference: str | None = None,
    ) -> dict[str, Any]:
        """Cria customer no Asaas. CPF/CNPJ é obrigatório em prod."""
        payload: dict[str, Any] = {
            "name": nome,
            "email": email,
            "mobilePhone": telefone,
            "externalReference": external_reference,
        }
        if cpf_cnpj:
            payload["cpfCnpj"] = cpf_cnpj
        # remove chaves None pra Asaas não reclamar
        payload = {k: v for k, v in payload.items() if v is not None}
        return await self._request("POST", "/customers", json=payload)

    async def atualizar_customer(
        self, customer_id: str, *, nome: str | None = None, email: str | None = None
    ) -> dict[str, Any]:
        payload = {k: v for k, v in {"name": nome, "email": email}.items() if v}
        return await self._request(
            "POST", f"/customers/{customer_id}", json=payload
        )

    # =================================================
    # Subscriptions (assinaturas recorrentes)
    # =================================================

    async def criar_assinatura(
        self,
        *,
        customer_id: str,
        valor_centavos: int,
        proximo_vencimento_iso: str,
        descricao: str,
        ciclo: str = "MONTHLY",
        billing_type: str | None = None,
    ) -> dict[str, Any]:
        """Cria assinatura mensal. `proximo_vencimento_iso` = YYYY-MM-DD."""
        bt = billing_type or settings.ASAAS_DEFAULT_BILLING_TYPE
        payload = {
            "customer": customer_id,
            "billingType": bt,
            "value": valor_centavos / 100.0,
            "nextDueDate": proximo_vencimento_iso,
            "cycle": ciclo,
            "description": descricao,
        }
        return await self._request("POST", "/subscriptions", json=payload)

    async def cancelar_assinatura(self, subscription_id: str) -> dict[str, Any]:
        return await self._request(
            "DELETE", f"/subscriptions/{subscription_id}"
        )

    async def atualizar_assinatura_valor(
        self, subscription_id: str, *, valor_centavos: int
    ) -> dict[str, Any]:
        """Usado quando o cliente troca de plano e o valor muda."""
        return await self._request(
            "POST",
            f"/subscriptions/{subscription_id}",
            json={"value": valor_centavos / 100.0},
        )

    # =================================================
    # Checkout (link de pagamento pro signup self-service)
    # =================================================

    async def gerar_link_pagamento(
        self,
        *,
        nome: str,
        valor_centavos: int,
        descricao: str,
        validade_dias: int = 7,
    ) -> dict[str, Any]:
        """Gera um payment link único.

        Útil pra signup: usuário escolhe plano → mostramos link pra pagar
        a primeira mensalidade.
        """
        from datetime import date, timedelta

        payload = {
            "name": nome,
            "value": valor_centavos / 100.0,
            "billingType": settings.ASAAS_DEFAULT_BILLING_TYPE,
            "chargeType": "DETACHED",
            "description": descricao,
            "endDate": (date.today() + timedelta(days=validade_dias)).isoformat(),
        }
        return await self._request("POST", "/paymentLinks", json=payload)


# ============================================================
# Helpers
# ============================================================


def _extrair_mensagem_erro(data: Any) -> str:
    """Tira a mensagem mais útil possível do payload de erro do Asaas."""
    if isinstance(data, dict):
        errors = data.get("errors")
        if isinstance(errors, list) and errors:
            primeiro = errors[0]
            if isinstance(primeiro, dict):
                return (
                    primeiro.get("description")
                    or primeiro.get("code")
                    or "Erro desconhecido do Asaas"
                )
        if data.get("message"):
            return str(data["message"])
    return f"Asaas devolveu erro: {data}"


# Singleton
asaas_client = AsaasClient()


__all__ = [
    "AsaasClient",
    "AsaasFalhouError",
    "AsaasIndisponivelError",
    "asaas_client",
]
