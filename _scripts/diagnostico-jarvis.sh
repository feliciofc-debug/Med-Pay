#!/bin/bash
# Diagnóstico rápido do Jarvis na VPS Contabo.
# Roda na VPS via: bash /tmp/diagnostico-jarvis.sh
#
# Verifica:
# - Status da sessão jarvis no Wuzapi
# - Webhook configurado (deve apontar pra https://medpag-api.onrender.com/api/whatsapp/webhook)
# - Última mensagem inbound recebida pelo Wuzapi

set -e

WUZAPI_URL="${WUZAPI_URL:-http://localhost:8082}"
TOKEN="${WUZAPI_TOKEN:-jarvis-byceo-2026}"

echo "=========================================="
echo "Diagnóstico Jarvis Wuzapi"
echo "URL: $WUZAPI_URL"
echo "=========================================="

echo ""
echo "1) STATUS da sessao:"
curl -s -H "Token: $TOKEN" "$WUZAPI_URL/session/status" | jq . || echo "  (sem jq, retorno bruto acima)"

echo ""
echo "2) WEBHOOK configurado:"
curl -s -H "Token: $TOKEN" "$WUZAPI_URL/webhook" | jq . || echo "  (sem jq)"

echo ""
echo "Se webhook estiver vazio ou apontando pra outro lugar, rode:"
echo ""
echo "  curl -X POST -H \"Token: $TOKEN\" -H \"Content-Type: application/json\" \\"
echo "    \"$WUZAPI_URL/webhook\" \\"
echo "    -d '{\"WebhookURL\":\"https://medpag-api.onrender.com/api/whatsapp/webhook\",\"Events\":[\"Message\"]}'"
echo ""
echo "Para forçar reconexão (se estiver com problema):"
echo "  curl -X POST -H \"Token: $TOKEN\" \"$WUZAPI_URL/session/logout\""
echo "  curl -X POST -H \"Token: $TOKEN\" -H \"Content-Type: application/json\" \\"
echo "    \"$WUZAPI_URL/session/connect\" \\"
echo "    -d '{\"Subscribe\":[\"Message\",\"ReadReceipt\",\"ChatPresence\",\"Presence\"],\"Immediate\":true}'"
echo "=========================================="
