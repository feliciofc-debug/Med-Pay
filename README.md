# MedPag

Sistema de processamento de pagamentos em massa para distribuidoras de pagamentos do setor de saúde.

Recebe planilhas de hospitais/clínicas/ONGs, valida CPFs e dados bancários, e gera arquivos CNAB 240 prontos para upload no internet banking da Unicred.

> **Status:** MVP completo, pronto para deploy em produção (Render + Vercel).
> Veja [`docs/DEPLOY.md`](docs/DEPLOY.md) para o passo a passo.

## Deploy em produção (Render + Vercel)

Veja o guia completo em [`docs/DEPLOY.md`](docs/DEPLOY.md).
Resumo:

```
Vercel (frontend Vite) ── HTTPS ──> Render (FastAPI + Worker + Postgres + Redis)
```

Custo estimado: **~$14-21/mês**. Tempo de deploy: ~60 min.

## Demonstração

Para demonstrar o sistema funcionando ponta a ponta sem conectar à Unicred real,
veja [`docs/DEMO_ROTEIRO.md`](docs/DEMO_ROTEIRO.md). Os scripts auxiliares:

```bash
# Gerar planilhas de demo com erros plantados (45 médicos no Santa Casa, 18 na Vida Nova)
python scripts/gerar_planilha_demo.py

# Simular a resposta do banco (lê .rem do MedPag, gera .ret)
python scripts/simular_banco_unicred.py CAMINHO_DO_REM
```

## Stack

**Backend:** Python 3.11 • FastAPI 0.115 • SQLAlchemy 2.0 (async) • Celery 5 • PostgreSQL 15 • Redis 7
**Frontend:** React 18 • TypeScript • Vite 5 • TailwindCSS 3 • TanStack Query • React Router 6
**Infra:** Docker Compose (dev) • Caddy/Traefik + Docker (prod sugerido)

## Quick Start (com Docker)

```bash
# 1) Gerar chaves seguras
python scripts/gerar_chaves.py
# Cole SECRET_KEY e ENCRYPTION_KEY no .env

# 2) Copiar template de variáveis de ambiente
cp .env.example .env
# Edite .env (já com as chaves do passo 1)

# 3) Subir os serviços
docker compose up -d

# 4) Rodar migrations (cria todas as tabelas)
docker compose exec backend alembic upgrade head

# 5) Criar usuário ADMIN (Thiago/Felício)
docker compose exec -e ADMIN_EMAIL=felicio@medpag.com -e ADMIN_SENHA=sua_senha_forte \
  backend python -m app.scripts.create_admin

# 6) Acessar
# Frontend:  http://localhost:5173
# Backend:   http://localhost:8000/docs
# Flower:    http://localhost:5555  (monitoramento Celery)
```

## Quick Start (desenvolvimento local sem Docker)

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Linux/Mac
pip install -r requirements.txt

# Tenha Postgres 15 e Redis 7 rodando localmente (porta padrão)
# Crie um banco chamado `medpag` no Postgres

alembic upgrade head
python -m app.scripts.create_admin

uvicorn app.main:app --reload --port 8000

# Em outro terminal: worker Celery
celery -A app.workers.celery_app worker --loglevel=info

# Frontend
cd frontend
npm install
npm run dev
```

## Fluxo do MVP (alinhado à operação Unicred)

```
1. CLIENTE envia planilha (upload no portal MedPag)
   ↓
2. SISTEMA valida automaticamente (CPF, banco, valor, duplicatas)
   ↓
3. APROVADOR vê dashboard com lotes aguardando
   ✅ verde   = ok
   ⚠️ amarelo = sugestão de correção
   ❌ vermelho = bloqueado
   ↓
4. APROVADOR clica "Aprovar lote inteiro"
   - Confirmação dupla (digite "APROVAR")
   - Sistema gera arquivo CNAB 240 .rem
   - Auditoria registrada com hash + timestamp + user
   ↓
5. APROVADOR baixa o .rem e sobe MANUALMENTE no internet banking Unicred
   ↓
6. BANCO processa e devolve arquivo .ret
   ↓
7. APROVADOR sobe o .ret aqui (POST /lotes/{id}/retorno)
   - Sistema concilia automaticamente
   - Cada pagamento marcado como PAGO ou NAO_PAGO
```

## Estrutura

```
medpag/
├── backend/
│   ├── app/
│   │   ├── api/             # Endpoints FastAPI
│   │   ├── core/            # Config, security, crypto, deps, exceptions
│   │   ├── models/          # SQLAlchemy
│   │   ├── schemas/         # Pydantic v2
│   │   ├── services/        # Regras de negócio (auth, lote, importacao, cnab_generator, cnab_parser, conciliacao, auditoria)
│   │   ├── validators/      # Pure functions (cpf, banco, valor)
│   │   ├── workers/         # Celery (celery_app + tasks)
│   │   ├── scripts/         # create_admin
│   │   └── main.py
│   ├── alembic/             # Migrations
│   ├── tests/               # pytest
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/      # Layout, StatusBadge, AprovacaoModal
│   │   ├── pages/           # Login, Dashboard, Upload, LoteDetalhe, LotesList
│   │   ├── hooks/           # useAuth
│   │   ├── lib/             # api (axios), utils (formatBRL)
│   │   └── types/           # Tipos compartilhados (espelham o backend)
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── Dockerfile
├── docs/
│   ├── ARCHITECTURE.md
│   ├── CNAB240_UNICRED.md
│   └── PROMPT_CURSOR.md
├── scripts/
│   └── gerar_chaves.py     # Gera SECRET_KEY + ENCRYPTION_KEY
├── docker-compose.yml
├── .env.example
├── .cursorrules            # Regras do projeto (fonte de verdade)
└── README.md
```

## Comandos úteis

```bash
# Testes
docker compose exec backend pytest -v
# Testes sem Docker (não precisa de DB pra rodar testes unitários):
cd backend && pytest tests/test_validators_*.py tests/test_crypto.py tests/test_security.py tests/test_cnab_*.py -v

# Lint e format
docker compose exec backend ruff check .
docker compose exec backend ruff format .

# Type check
docker compose exec backend mypy app/

# Migrations
docker compose exec backend alembic revision --autogenerate -m "descrição"
docker compose exec backend alembic upgrade head
docker compose exec backend alembic downgrade -1

# Shell do banco
docker compose exec postgres psql -U medpag medpag

# Logs
docker compose logs -f backend
docker compose logs -f worker

# Reset total (CUIDADO: apaga dados!)
docker compose down -v
docker compose up -d
docker compose exec backend alembic upgrade head
```

## Rodar testes unitários (sem precisar do Postgres)

Os validators (CPF, banco, valor), crypto, security, parser e gerador CNAB são puros e podem ser testados sem banco:

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

Resultado esperado: 80+ testes passando, cobrindo:
- Validação de CPF (sequências fake, dígitos, sugestão de correção)
- Validação bancária (Unicred + tabela FEBRABAN)
- Validação de valor (formato BR/US, suspeito, zero)
- Criptografia Fernet (roundtrip, hash determinístico, mascaramento)
- JWT (access/refresh, tokens inválidos/expirados, senhas)
- Importação de planilha (XLSX/CSV, mapeamento de colunas, idempotência)
- CNAB Generator (240 chars por linha, totalizadores, hash, sem acentos)
- CNAB Parser (códigos de ocorrência, pagos/não pagos)

## Documentação

- **`.cursorrules`** — regras do projeto, princípios, padrões, roadmap (FONTE DE VERDADE)
- **`docs/ARCHITECTURE.md`** — decisões arquiteturais e fluxo completo
- **`docs/CNAB240_UNICRED.md`** — especificação do layout CNAB Unicred

## Roadmap

### ✅ Fase 1 (MVP) — IMPLEMENTADO
- Setup Docker + Compose com Postgres + Redis + backend + worker + Flower + frontend
- Models completos (User, Cliente, Beneficiário, Lote, Pagamento, EmpresaConfig, Auditoria)
- Auth JWT (login, refresh, logout, /me) com cookie httpOnly
- Upload XLSX/CSV com idempotência via hash SHA-256
- Mapeamento heurístico de colunas + override por cliente
- Validação de CPF com sugestão de correção (zero perdido pelo Excel)
- Validação bancária (Unicred + tabela FEBRABAN)
- Detecção de duplicatas e valores suspeitos
- Worker Celery para processamento em background
- Tela de revisão com semáforo (verde/amarelo/vermelho)
- Aprovação dupla com confirmação textual + totalizadores
- Geração de CNAB 240 Unicred (Header arq + Header lote + Segmentos A/B + Trailers)
- Download do `.rem`
- Upload do `.ret` + parser + conciliação automática
- Auditoria completa de cada operação financeira
- Dashboard com lotes pendentes / aprovados / enviados

### 🔜 Fase 2
- Cadastro persistente de beneficiários (memória entre lotes)
- Mapeamento de colunas salvo automaticamente por cliente
- Notificações por e-mail (cliente + aprovador)
- Suporte multi-banco (Itaú, BB, Bradesco, Sicredi, Sicoob)
- Portal do cliente (upload sem login)
- Relatórios PDF por cliente

### 🔜 Fase 3
- Integração SFTP/API Unicred Empresarial
- Suporte a PIX em lote
- App mobile com aprovação biométrica
- Multi-tenant completo

## Suporte

Felício — fundador e responsável técnico
