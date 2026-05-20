# Arquitetura do MedPag

## Visão geral

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React + TS)                       │
│                                                                     │
│  Dashboard Thiago  Lote (revisar)  Cadastros  Auditoria  Login     │
│                                                                     │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTPS / JSON / JWT
                             │
┌────────────────────────────▼────────────────────────────────────────┐
│                      BACKEND (FastAPI + Async)                      │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │   API    │→ │ Services │→ │  Validators  │  │   Workers      │  │
│  │ (rotas)  │  │ (regras) │  │ (CPF, banco, │  │   (Celery)     │  │
│  │          │  │          │  │  CNAB, etc)  │  │  - processar   │  │
│  │          │  │          │  │              │  │  - email       │  │
│  └──────────┘  └────┬─────┘  └──────────────┘  └────────────────┘  │
│                     │                                                │
└─────────────────────┼────────────────────────────────────────────────┘
                      │
        ┌─────────────┼──────────────┐
        │             │              │
   ┌────▼───┐   ┌─────▼────┐   ┌─────▼────┐
   │Postgres│   │  Redis   │   │  Files   │
   │(dados) │   │(fila/    │   │ (upload/ │
   │        │   │ cache)   │   │  CNAB)   │
   └────────┘   └──────────┘   └──────────┘
```

## Decisões importantes

### Por que async em tudo?

Volume de 5.000 pagamentos/mês não é alto, mas validação de planilha grande
pode demorar segundos. Async permite que o backend não trave durante
processamento. Também facilita integrações futuras com APIs bancárias.

### Por que worker separado (Celery)?

Upload de planilha de 5.000 linhas pode demorar 30-60s para validar tudo.
Em vez de fazer o usuário esperar, o endpoint joga na fila Redis e o
worker processa em background. Frontend faz polling do status.

### Por que criptografia em campo específico (não no banco inteiro)?

- LGPD exige tratamento especial pra dado sensível, não pra tudo
- Performance: queries em campos não-sensíveis são rápidas
- Backup: dump do banco em mãos erradas só expõe metadata, não dados pessoais
- Auditoria: podemos logar "Thiago acessou pagamento X" sem expor CPF

### Por que valores em centavos (int) em vez de Decimal?

- Operações matemáticas em int são exatas. Decimal tem casos de borda.
- Postgres tem nativo `INTEGER` mas `NUMERIC` é mais lento
- Conversão pra reais só acontece na exibição (frontend)
- **REGRA:** banco armazena centavos. Frontend exibe reais. API conversa em centavos.

### Por que single-tenant no MVP?

A empresa do Thiago é o primeiro cliente. Tornar multi-tenant agora =
complexidade enorme sem ganho real. Quando vier o segundo cliente, refatoramos
adicionando coluna `tenant_id` em todas as tabelas + middleware de filtro.

Custo de refatorar depois: ~2 semanas. Ganho de não fazer agora: economiza
30% do tempo do MVP.

### Por que JWT em cookie (não localStorage)?

- XSS: token em localStorage é roubável por qualquer script malicioso
- Cookie httpOnly + Secure + SameSite=Strict bloqueia XSS e CSRF
- Em dev usamos localStorage por simplicidade; produção SEMPRE cookie

## Fluxo de processamento de um lote

```
1. CLIENTE ENVIA PLANILHA
   - Email com anexo → IMAP monitor (worker)
   - Upload via portal → endpoint POST /api/lotes/upload
   - Em ambos os casos, dispara create_lote() service

2. CREATE_LOTE
   - Calcula hash SHA-256 do conteúdo
   - Verifica idempotência (hash já existe? retorna lote anterior)
   - Cria registro Lote com status RECEBIDO
   - Salva arquivo bruto em disco/S3
   - Enfileira task processar_lote.delay(lote_id)
   - Retorna 202 Accepted com lote_id

3. WORKER: PROCESSAR_LOTE
   - Atualiza status → PROCESSANDO
   - Lê planilha (pandas)
   - Aplica mapeamento de colunas do cliente (se houver)
   - Para cada linha:
     - validar_cpf() → status do CPF
     - validar_dados_bancarios() → status bancário
     - detectar_valor_suspeito() → comparado com histórico do beneficiário
     - detectar_duplicata() → mesmo CPF+valor neste mês?
     - Determina status final do pagamento
     - Cria registro Pagamento (com criptografia)
   - Atualiza totalizadores do Lote
   - Atualiza status → AGUARDANDO_REVISAO
   - Envia notificação pra Thiago

4. THIAGO REVISA E APROVA
   - GET /api/lotes/{id} → carrega lote com pagamentos
   - Frontend mostra semáforo, filtros, sugestões
   - PUT /api/pagamentos/{id} → editar dados específicos (aceitar sugestão)
   - POST /api/lotes/{id}/aprovar → aprovação dupla com confirmação

5. APROVAR_LOTE
   - Verifica permissão (Thiago = APROVADOR)
   - Valida que lote está em AGUARDANDO_REVISAO
   - Gera arquivo CNAB 240
   - Calcula hash SHA-256 do arquivo
   - Salva arquivo em disco/S3
   - Cria registro Auditoria com hash + user_id + timestamp
   - Atualiza Lote: status=APROVADO, hash_arquivo_cnab, aprovado_por_id, aprovado_at
   - Atualiza Pagamentos: status=APROVADO
   - Retorna URL pra download do arquivo

6. THIAGO BAIXA E ENVIA AO BANCO (manual)
   - GET /api/lotes/{id}/cnab → download do .rem
   - Faz upload no internet banking da Unicred
   - Sistema atualiza status → ENVIADO_BANCO (botão manual no dashboard)

7. RETORNO DO BANCO
   - Thiago baixa arquivo .ret do internet banking
   - POST /api/lotes/{id}/retorno → upload do .ret
   - Worker processa retorno
   - Atualiza cada Pagamento: status PAGO ou NAO_PAGO + motivo
   - Lote → CONCILIADO
   - Gera relatório PDF pro cliente (hospital)
```

## Camadas e responsabilidades

| Camada | Responsabilidade | NÃO faz |
|--------|------------------|---------|
| API (`app/api/`) | Receber HTTP, validar input (Pydantic), chamar service, retornar response | Lógica de negócio, acesso direto ao banco |
| Services (`app/services/`) | Orquestrar operações, transações, regras de negócio | Receber HTTP, formatar response |
| Validators (`app/validators/`) | Validar dados puros (CPF, banco) | Acessar banco, IO |
| Models (`app/models/`) | Estrutura de tabelas (SQLAlchemy) | Lógica de negócio complexa |
| Schemas (`app/schemas/`) | Input/output da API (Pydantic) | Lógica |
| Workers (`app/workers/`) | Tasks longas em background | Responder HTTP |
| Core (`app/core/`) | Config, segurança, conexões | Lógica de domínio |

## Tratamento de erros

```python
# Exceções customizadas em app/core/exceptions.py
class MedPagException(Exception): ...
class LoteJaProcessadoError(MedPagException): ...
class LoteNaoAprovavelError(MedPagException): ...
class PermissaoNegadaError(MedPagException): ...
class ValidacaoError(MedPagException): ...

# Handler global em app/main.py
@app.exception_handler(MedPagException)
async def handle_medpag_error(request, exc):
    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "error": {
                "code": exc.__class__.__name__,
                "message": str(exc),
            }
        }
    )
```

## Logs estruturados

Usar `structlog` em vez de logging padrão. Vantagens:

- Logs em JSON (parseável)
- Contexto automático (request_id, user_id)
- Mascaramento automático de campos sensíveis

```python
import structlog
log = structlog.get_logger()

# Bom
log.info("lote.aprovado", lote_id=str(lote.id), valor_total=lote.valor_total_centavos)

# RUIM (nunca CPF em log)
log.info("pagamento_criado", cpf="12345678909")  # ❌

# Certo (mascarado)
log.info("pagamento_criado", cpf=mask_cpf("12345678909"))  # XXX.XXX.XXX-09
```

## Próximos passos para o Cursor

Veja `.cursorrules` na raiz para roadmap detalhado de implementação.

Começar implementando, nesta ordem:

1. Migrations (Alembic init + primeira migration com os models)
2. Service de criptografia + hashing (já criado em `core/crypto.py`)
3. Auth completo (registro admin, login, refresh)
4. Service de importação de planilha (`services/importacao.py`)
5. Service de processamento de lote (`services/processamento.py`)
6. Worker Celery (`workers/processar_lote.py`)
7. Service de geração CNAB (`services/cnab_generator.py`)
8. API completa (rotas)
9. Frontend (telas)
