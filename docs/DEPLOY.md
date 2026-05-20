# Deploy do MedPag — Render + Vercel

Guia passo a passo para colocar o MedPag em produção em ~60 minutos.

```
┌────────────────────────────────────────────────────────────┐
│  USUÁRIO                                                   │
│  abre  →  https://medpag.vercel.app                        │
└─────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │  VERCEL — FRONTEND          │
        │  React + Vite estático      │
        │  CDN global (rápido)        │
        └──────────────┬──────────────┘
                       │ HTTPS
                       ▼
        ┌─────────────────────────────┐
        │  RENDER — BACKEND           │
        │  ├── FastAPI (web)          │
        │  ├── Worker Celery          │
        │  ├── Postgres 15            │
        │  └── Redis (Key Value)      │
        └─────────────────────────────┘
```

## Pré-requisitos

- Conta no GitHub (já tem)
- Conta no [Render](https://render.com) (login via GitHub é o mais rápido)
- Conta no [Vercel](https://vercel.com) (login via GitHub também)
- Projeto no GitHub: `https://github.com/feliciofc-debug/Med-Pay`

## Passo 1 — Gerar a chave de criptografia (1 min)

A `ENCRYPTION_KEY` precisa ser uma chave Fernet válida (44 chars base64).
**Não pode** ser gerada automaticamente pelo Render.

Na máquina local, rode:

```bash
cd backend
python ../scripts/gerar_chaves.py
```

Vai imprimir algo assim:

```
SECRET_KEY=zXq3...44-chars-de-base64...=
ENCRYPTION_KEY=xK7-Fernet-de-44-chars-base64=
```

**Anote a `ENCRYPTION_KEY`** — vai colar no dashboard do Render daqui a pouco.
(A `SECRET_KEY` o Render vai gerar sozinho via `generateValue: true`.)

## Passo 2 — Deploy do backend no Render (15 min)

### 2.1 Conectar GitHub no Render

1. Acesse https://render.com → **Get Started** → entre com GitHub
2. Autorize o Render a ler seus repositórios (escolha o `Med-Pay`)

### 2.2 Criar o Blueprint

1. No dashboard do Render, clique em **New** → **Blueprint**
2. Selecione o repositório `feliciofc-debug/Med-Pay`
3. Render vai detectar o `render.yaml` automaticamente
4. Confira que ele lista: `medpag-postgres`, `medpag-redis`, `medpag-api`, `medpag-worker`
5. Clique em **Apply**

Aguarde ~10 min — Render vai:
- Criar o Postgres
- Criar o Key Value (Redis)
- Buildar o Docker do backend (primeiro build é o mais demorado)
- Subir o web service e o worker
- Falhar a primeira vez porque `ENCRYPTION_KEY` ainda não foi setada

### 2.3 Definir os secrets

No dashboard, abra o serviço **medpag-api** → aba **Environment**:

1. **`ENCRYPTION_KEY`** → cole o valor que você gerou no Passo 1
2. **`ADMIN_SENHA`** → escolha uma senha forte (8+ chars, mix de letras/números)
   - Esta é a senha pra você logar como **felicio@medpag.com.br** (ADMIN)

Faça o mesmo no serviço **medpag-worker**:

1. **`ENCRYPTION_KEY`** → cole o **mesmo valor** que colocou no api
   (precisa ser idêntico, senão worker e api não conseguem descriptografar os mesmos dados)

Clique em **Save Changes** em ambos. Os serviços vão reiniciar automaticamente.

### 2.4 Verificar que está no ar

Render vai te dar URLs tipo:

- API: `https://medpag-api.onrender.com`
- Health check: `https://medpag-api.onrender.com/health` (deve retornar `{"status":"ok",...}`)

Se der 500, abra os logs do `medpag-api` no dashboard.

**Importante:** no primeiro boot, o `startup.sh` roda:
- `alembic upgrade head` (cria todas as tabelas)
- `create_admin` (cria o usuário felicio@medpag.com.br)
- `seed_demo` (cria Hospital Santa Casa, Clínica Vida Nova, usuário thiago@medpag.com.br)

## Passo 3 — Deploy do frontend no Vercel (5 min)

### 3.1 Conectar GitHub no Vercel

1. Acesse https://vercel.com → **Sign Up** → entre com GitHub
2. Autorize o Vercel a ler seus repositórios

### 3.2 Importar o projeto

1. Dashboard Vercel → **Add New** → **Project**
2. Selecione `feliciofc-debug/Med-Pay`
3. Na tela de configuração:
   - **Framework Preset:** Vite (detecta automaticamente)
   - **Root Directory:** `frontend` ⚠️ importante
   - **Build Command:** deixa o padrão (`npm run build`)
   - **Output Directory:** `dist`
4. Em **Environment Variables**, adicione:
   - **Name:** `VITE_API_URL`
   - **Value:** `https://medpag-api.onrender.com` (a URL do backend no Render)
5. Clique em **Deploy**

Aguarde ~2 min. No fim, o Vercel te dá uma URL tipo `https://med-pay.vercel.app`.

### 3.3 Ajustar CORS no backend

Anote a URL exata que o Vercel gerou. Volte no Render:

1. **medpag-api** → **Environment** → variável `CORS_ORIGINS`
2. Cole a URL do Vercel (separadas por vírgula se tiver mais de uma):
   ```
   https://med-pay.vercel.app,https://med-pay-feliciofc-debug.vercel.app
   ```
3. **Save Changes** — backend reinicia.

## Passo 4 — Login e teste rápido (5 min)

1. Abra `https://med-pay.vercel.app/login`
2. **Login do admin (Felício):**
   - Email: `felicio@medpag.com.br` (ou o `ADMIN_EMAIL` que você setou)
   - Senha: a senha que você definiu em `ADMIN_SENHA`
3. **Login do aprovador (Thiago):**
   - Email: `thiago@medpag.com.br`
   - Senha: `thiago123` (senha padrão do seed; **trocar depois**)
4. No dashboard, você deve ver os dois clientes de demonstração:
   - Hospital Santa Casa de Misericórdia
   - Clínica Vida Nova

Se aparecer, **está no ar**.

## Passo 5 — Demo end-to-end com a planilha (10 min)

Veja [`DEMO_ROTEIRO.md`](./DEMO_ROTEIRO.md) para o passo a passo da
demonstração com a planilha do Hospital Santa Casa.

## Troubleshooting

### "Cannot connect to database" no log do Render

A primeira inicialização pode falhar se o Postgres ainda não está pronto.
Espere 1-2 min e clique em **Manual Deploy** → **Deploy latest commit** no `medpag-api`.

### Login retorna 401 mesmo com senha certa

Provavelmente o `ENCRYPTION_KEY` é diferente entre `medpag-api` e `medpag-worker`.
Confirme que está **idêntico** nos dois.

### Frontend retorna erro de CORS

A URL do Vercel não está no `CORS_ORIGINS` do backend. Adicione e salve.
Lembre-se: cada deploy do Vercel gera URLs de preview. Em produção,
configure um domínio fixo no Vercel pra evitar mudar `CORS_ORIGINS` toda hora.

### Backend "dorme" e demora pra responder

O plano `starter` do Render NÃO dorme. Se ainda assim tiver lentidão,
verifique se ficou no plano `free` por engano (free dorme após 15 min).

## Custos mensais estimados

| Serviço | Plano | Custo/mês |
|---|---|---|
| Render Postgres (free 90d) | Free | $0 (depois $7) |
| Render Key Value (Redis) | Free 25MB | $0 |
| Render Web (backend) | Starter | $7 |
| Render Worker | Starter | $7 |
| Vercel Hobby | Free | $0 |
| **Total** | | **$14 (depois $21)** |

Pra demo do Thiago: free do Postgres + starter do resto cobre tudo confortavelmente.

## Próximos passos depois do deploy

- [ ] Comprar domínio próprio (`medpag.com.br`) e conectar no Vercel
- [ ] Habilitar HTTPS automático (já vem de fábrica no Vercel e Render)
- [ ] Configurar alertas de saúde (Render manda email se cair)
- [ ] Backup do Postgres (Render faz daily backup automático no Starter+)
- [ ] Monitoramento de erros (Sentry, Logtail, etc — Fase 2)
