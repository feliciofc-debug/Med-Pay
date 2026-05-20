# PROMPT MESTRE — Cole isso no Cursor (Composer ou Chat)

> **Felício, use este prompt no Cursor pra ele entender o projeto inteiro.**
> Cole o conteúdo abaixo na primeira interação com o Cursor (Composer Agent
> ou Chat com Opus). Ele vai ler todos os arquivos relevantes e ficar
> calibrado pro projeto.

---

## Prompt para Cursor

```
Você é o desenvolvedor sênior do projeto MedPag. Antes de qualquer coisa,
leia OBRIGATORIAMENTE estes arquivos na raiz do projeto:

1. .cursorrules — regras inegociáveis, princípios, roadmap
2. README.md — visão geral e setup
3. docs/ARCHITECTURE.md — decisões arquiteturais e fluxo completo
4. docs/CNAB240_UNICRED.md — layout técnico do arquivo CNAB
5. backend/app/validators/cpf.py — exemplo do padrão de código esperado
6. backend/app/validators/banco.py — outro exemplo do padrão
7. backend/app/models/__init__.py + todos os arquivos em models/ — estrutura de dados

Depois de ler, me confirme em uma frase curta:
- "Li o projeto MedPag. Sou o dev sênior responsável. Próximo passo é X."

Onde X é a primeira tarefa do roadmap (FASE 1 do .cursorrules) que ainda
não foi feita.

REGRAS DE OURO QUE NUNCA QUEBRA:
1. CPF e conta bancária sempre criptografados (Fernet) + hash pra busca
   + mascarado pra exibição. NUNCA em plaintext em log.
2. Valores monetários SEMPRE em centavos (int). Reais só na exibição.
3. Aprovação humana é obrigatória pra gerar CNAB. Sistema NUNCA decide sozinho.
4. Toda operação financeira gera entrada de Auditoria com hash + user + timestamp.
5. Idempotência via hash SHA-256 do conteúdo. Reenvio = retorna lote existente.
6. Type hints obrigatórios. Mypy strict. Pydantic v2 nos schemas.
7. Funções pequenas (<50 linhas). Lógica em services, não em endpoints.
8. Testes pytest pra todo código financeiro (mínimo: caminho feliz + 2 erros).
9. Português nas mensagens e docstrings. Inglês nos identificadores.
10. Antes de qualquer mudança grande, ME PERGUNTE. Não assuma.

ESTILO DE TRABALHO:
- Implemente uma camada de cada vez (model → schema → service → endpoint → teste)
- Após cada implementação, rode os testes e me mostre o resultado
- Faça commits pequenos com mensagens em português
- Se encontrar uma decisão arquitetural que não está no docs/, ME PERGUNTE
  antes de inventar

COMECE LENDO OS ARQUIVOS LISTADOS ACIMA.
```

---

## Como usar no Cursor

### Opção 1: Composer Agent (recomendado)

1. Abra o projeto no Cursor
2. `Cmd+I` (ou `Ctrl+I` no Windows) pra abrir o Composer
3. Selecione modo **Agent** + modelo **Claude Opus** ou **Sonnet 4.5**
4. Cole o prompt acima
5. Deixe ele ler os arquivos e propor o próximo passo

### Opção 2: Chat com contexto

1. `Cmd+L` pra abrir o Chat
2. Use `@Codebase` no início pra ele indexar tudo
3. Cole o prompt
4. Vá pedindo implementação tarefa por tarefa

### Opção 3: Para tarefas específicas

Quando quiser uma feature nova, use este template:

```
Refaça [funcionalidade X] seguindo as regras do .cursorrules.

Contexto:
- O que existe hoje: [descrever ou pedir pra ler]
- O que precisa mudar: [especificar]
- Critérios de aceitação:
  1. [critério 1]
  2. [critério 2]

Antes de começar, me confirme o plano de implementação em bullets.
Não escreva código antes de eu aprovar o plano.
```

---

## Estado atual do projeto (o que já está pronto)

Pronto pra desenvolver em cima:

- ✅ `.cursorrules` completo
- ✅ `docker-compose.yml` com Postgres + Redis + backend + worker
- ✅ `.env.example` com todas as variáveis
- ✅ Backend: configurações (`core/config.py`)
- ✅ Backend: criptografia (`core/crypto.py`) — Fernet + hash + máscara
- ✅ Backend: segurança (`core/security.py`) — JWT + bcrypt
- ✅ Backend: database (`core/database.py`) — async SQLAlchemy 2.0
- ✅ Backend: validators CPF e banco com **51 testes passando**
- ✅ Backend: models completos (User, Cliente, Beneficiario, Lote, Pagamento, Auditoria)
- ✅ Backend: `main.py` com factory FastAPI
- ✅ Docs: arquitetura + CNAB Unicred detalhado

Falta implementar (FASE 1):

- ⏳ Migrations Alembic (rodar `alembic init` e gerar primeira migration)
- ⏳ Schemas Pydantic (request/response)
- ⏳ Service de auth (registro/login/refresh)
- ⏳ Service de importação de planilha
- ⏳ Service de processamento de lote (orquestra validações)
- ⏳ Service de geração CNAB 240 Unicred
- ⏳ Workers Celery
- ⏳ Endpoints da API
- ⏳ Frontend React inteiro
- ⏳ Script de criação de usuário admin

---

## Comandos úteis durante desenvolvimento

```bash
# Subir ambiente
docker-compose up -d

# Ver logs
docker-compose logs -f backend
docker-compose logs -f worker

# Rodar testes
docker-compose exec backend pytest -v

# Rodar testes específicos
docker-compose exec backend pytest tests/test_validators_cpf.py -v

# Lint e format
docker-compose exec backend ruff check . --fix
docker-compose exec backend ruff format .

# Type check
docker-compose exec backend mypy app/

# Migrations
docker-compose exec backend alembic revision --autogenerate -m "descrição"
docker-compose exec backend alembic upgrade head
docker-compose exec backend alembic downgrade -1

# Shell do banco
docker-compose exec postgres psql -U medpag medpag

# Reset total (cuidado: apaga tudo!)
docker-compose down -v
docker-compose up -d
docker-compose exec backend alembic upgrade head
```

---

## Workflow recomendado

1. Abra o Cursor no projeto
2. Cole o **Prompt Mestre** acima no Composer (modo Agent)
3. Deixa ele ler tudo e propor o primeiro passo
4. Aprove ou ajuste o plano
5. Deixe ele implementar
6. Revise o código (você é o sócio majoritário, o código é seu!)
7. Rode os testes
8. Commite
9. Próxima tarefa

**Lembre-se:** o Cursor é uma ferramenta. Você é o engenheiro. Revisar
cada linha de código financeiro não é paranoia, é responsabilidade.

Boa sorte! 🚀
