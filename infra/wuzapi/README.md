# Wuzapi (WhatsApp não oficial) — Setup na VPS

Servidor Wuzapi que o Med-Pag usa pra falar com o WhatsApp via **Jarvis**
(módulo `/app/admin/whatsapp`).

> ⚠️ **Não é a API oficial Meta.** É baseado no whatsmeow (mesmo
> protocolo do WhatsApp Web). Pode ser banido se for usado pra spam ou
> volume muito alto. Para uso pessoal/interno (sócios, gestores) é OK.

---

## Pré-requisitos na Contabo

```bash
# Ubuntu 22.04 / Debian 12 — instala Docker
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# (logout / login pra aplicar o grupo)
```

---

## Instalação (5 minutos)

```bash
# 1) Cria pasta e baixa os arquivos do compose
sudo mkdir -p /opt/wuzapi
sudo chown $USER /opt/wuzapi
cd /opt/wuzapi

# Copie pra cá os arquivos:
#   - docker-compose.yml
#   - .env.example  (renomeie pra .env e edite os valores)
#
# Tip: se já está no repo Med-Pag clonado na VPS:
#   cp /caminho/Med-Pay/infra/wuzapi/* /opt/wuzapi/

cp .env.example .env

# 2) Gere segredos fortes
openssl rand -hex 32   # → cole em WUZAPI_ADMIN_TOKEN
openssl rand -hex 16   # → cole em WUZAPI_ENCRYPTION_KEY (32 chars)
openssl rand -hex 16   # → cole em WUZAPI_HMAC_KEY (32 chars)
openssl rand -base64 24  # → cole em WUZAPI_DB_PASSWORD

# Edite o .env com seu editor favorito
nano .env

# 3) Suba os contêineres
docker compose up -d

# 4) Confere se está rodando
docker compose ps
docker compose logs --tail=50 wuzapi

# 5) Health check da API
curl http://localhost:8080/
```

---

## Firewall (UFW)

A porta 8080 precisa ser acessível pelo backend Med-Pag (Render).
Você tem duas opções:

### Opção A (mais simples, menos seguro)

Liberar 8080 pra todo mundo. Wuzapi tem auth via token, então é OK.

```bash
sudo ufw allow 8080/tcp
sudo ufw reload
```

### Opção B (recomendada): Nginx + HTTPS

Coloque Nginx na frente, com Let's Encrypt:

```nginx
server {
    listen 443 ssl http2;
    server_name wuzapi.seudominio.com.br;

    ssl_certificate     /etc/letsencrypt/live/.../fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/.../privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 120s;
    }
}
```

E no Med-Pag, configure `WUZAPI_URL=https://wuzapi.seudominio.com.br`.

---

## Configurar no Med-Pag

No backend (Render → Environment), adicione:

```
WUZAPI_URL=http://IP_DA_CONTABO:8080
WUZAPI_ADMIN_TOKEN=mesmo_que_no_.env_da_VPS
WUZAPI_WEBHOOK_SECRET=opcional_secret_pra_blindar_webhook
GROQ_API_KEY=gsk_...  (https://console.groq.com/keys)
```

Depois:

1. No painel do Med-Pag, vá em **Admin → Jarvis (WhatsApp)**.
2. Clique em **Conectar WhatsApp** → escaneie o QR no app.
3. Autorize seu próprio número em **Números autorizados**.
4. Mande "bom dia" no WhatsApp do bot. O Jarvis responde 🤖.

---

## Comandos úteis na VPS

```bash
# Ver logs em tempo real
docker compose logs -f wuzapi

# Reiniciar só o Wuzapi (não derruba o banco)
docker compose restart wuzapi

# Atualizar imagem do Wuzapi
docker compose pull wuzapi
docker compose up -d wuzapi

# Backup do banco (sessões WhatsApp)
docker exec wuzapi-postgres pg_dump -U wuzapi_user wuzapi_db \
  | gzip > wuzapi-backup-$(date +%Y%m%d).sql.gz

# Espaço em disco do volume
docker system df -v | grep wuzapi
```

---

## Troubleshooting

### "Cannot connect" no painel do Med-Pag

- Verifica se a porta 8080 está aberta no firewall da Contabo (`sudo ufw status`)
- Verifica se o `WUZAPI_URL` no Render aponta pro IP/domínio correto
- Testa do laptop: `curl http://IP_DA_CONTABO:8080/` deve devolver JSON

### QR não aparece

- O Wuzapi às vezes precisa de um POST `/session/connect` antes do GET `/session/qr`. O Med-Pag já faz isso. Aguarde 3-5s e clique em "Renovar QR Code".
- Se o WhatsApp já estava conectado em outro lugar, desconecte primeiro.

### Mensagens não chegam no Med-Pag

- Confira que o webhook foi configurado: vá no painel Med-Pag → Jarvis → veja se aparece "Status: CONECTADA"
- Veja os logs do Wuzapi: `docker compose logs --tail=200 wuzapi | grep webhook`
- Se o Med-Pag estiver atrás de Cloudflare, libere a URL do webhook
