# Roteiro de Demonstração — MedPag

Como mostrar o sistema funcionando ponta a ponta para o Thiago (ou qualquer
cliente). Roteiro de 15-20 minutos.

## Antes da reunião — checklist (5 min)

- [ ] Plataforma no ar: `https://med-pay.vercel.app` abre o login
- [ ] Login do **Felício** funcionando (email + senha que você setou)
- [ ] Login do **Thiago** funcionando (`thiago@medpag.com.br` / `thiago123`)
- [ ] Dashboard mostra os 2 clientes de demo (Santa Casa + Vida Nova)
- [ ] Planilha de demo gerada: `planilhas-demo/planilha-hospital-santa-casa-novembro-2026.xlsx`
- [ ] Computador com 2 janelas/abas prontas:
  - Aba 1: login do hospital (vai logar como felicio = ADMIN aprovando como cliente)
  - Aba 2: login do Thiago (vai aprovar como o aprovador final)
- [ ] Internet boa
- [ ] Telão/projetor testado (se for apresentação ao vivo)

## Gerar a planilha de demo (se ainda não gerou)

```bash
cd backend
python ../scripts/gerar_planilha_demo.py
```

Cria:
- `planilhas-demo/planilha-hospital-santa-casa-novembro-2026.xlsx` (45 médicos)
- `planilhas-demo/planilha-clinica-vida-nova-novembro-2026.xlsx` (18 médicos)

## Roteiro de demonstração

### Passo 1 — Abertura (2 min)

> **Frase de abertura:**
> "Thiago, deixa eu te mostrar como ficaria a operação se o Hospital Santa
> Casa estivesse usando o MedPag. Vou interpretar dois papéis: primeiro
> o financeiro do hospital subindo a planilha, depois você aprovando."

### Passo 2 — Hospital sobe a planilha (3 min)

1. Aba 1 — login como hospital (use `felicio@medpag.com.br` por enquanto;
   na próxima fase teremos login específico do cliente)
2. Dashboard → **Novo lote**
3. Selecione cliente: **Hospital Santa Casa de Misericórdia**
4. Faça upload da planilha `planilha-hospital-santa-casa-novembro-2026.xlsx`
5. Aguarde o processamento (deve levar segundos)

> **Comentário:**
> "Note que o sistema já leu as 45 linhas, identificou as colunas
> automaticamente — CPF, nome, banco, agência, conta, valor — e
> mostrou um resumo."

### Passo 3 — Mostrar o semáforo (5 min)

A tela de revisão vai mostrar:
- ~38 linhas verdes (ok)
- ~4 linhas amarelas (atenção)
- ~3 linhas vermelhas (bloqueado)

> **Comentário em cada cor:**
> - **Verde:** "Esses 38 médicos têm CPF válido, banco válido, valor normal —
>   pode pagar sem preocupação."
> - **Amarelo:** "Aqui tem 2 CPFs que vieram com 10 dígitos —
>   provavelmente o Excel comeu o zero da frente. O sistema sugere a correção.
>   Olha: 'CPF 234567890 tem 10 dígitos. Sugestão: 02345678909.' Você só
>   clica em 'Aceitar sugestão'."
> - **Vermelho:** "Esses 3 estão bloqueados — um tem CPF com sequência
>   inválida (1, 2, 3, 4...), outro tem banco com código 999 que não existe
>   no Brasil, e outro tem linha duplicada — mesma pessoa, mesmo valor,
>   provavelmente engano do hospital."

**Pontos para enfatizar:**
- O sistema NÃO corrige nada sozinho. Ele **sugere**. O humano decide.
- Erros que iam virar estorno (semana de retrabalho) são pegos **antes** do dinheiro sair.
- Sem isso, o Thiago paga 45 médicos e descobre 3 dias depois que 3 deram erro.

### Passo 4 — Hospital envia para aprovação (1 min)

1. Aceite as sugestões amarelas (clique em "Aceitar correção" em cada uma)
2. Corrija ou bloqueie as vermelhas (pode deixar bloqueadas pra simular o cenário real)
3. Clique em **Enviar para aprovação**

> **Comentário:**
> "Pronto, o hospital já fez a parte dele. Agora a remessa cai na sua bancada."

### Passo 5 — Thiago aprova (3 min)

1. Aba 2 — login como **Thiago** (`thiago@medpag.com.br` / `thiago123`)
2. Dashboard — você vê: "Hospital Santa Casa tem 1 lote aguardando aprovação"
3. Clique no lote
4. Veja o resumo: 42 pagamentos aprovados, R$ X total, 3 bloqueados
5. Clique em **Aprovar lote**
6. Modal de confirmação: digite **APROVAR** e confirme

> **Comentário:**
> "Confirmação dupla pra evitar clique acidental. O sistema vai gerar o
> arquivo CNAB da Unicred com a conta do hospital — não da sua. Quem paga
> é o hospital, você só processa."

### Passo 6 — Baixar o arquivo CNAB (1 min)

1. Após aprovação, o sistema mostra: **Baixar arquivo de remessa (.rem)**
2. Baixe o arquivo

> **Comentário:**
> "Aqui é onde no mundo real você sobe esse arquivo no internet banking
> da Unicred do hospital. Vamos simular a resposta do banco em segundos."

### Passo 7 — Simular o retorno do banco (2 min)

No terminal:

```bash
python scripts/simular_banco_unicred.py CAMINHO_DO_REM_BAIXADO
```

Gera um arquivo `.ret` simulando que a Unicred processou:
- ~92% pagos com sucesso (código BD)
- ~8% rejeitados (saldo insuficiente, conta inválida, conta inexistente)

> **Comentário:**
> "Esse arquivo .ret é exatamente o formato que a Unicred devolveria
> 24h depois. No mundo real você ia baixar do internet banking deles.
> Aqui o script gera um realista pra gente fechar o ciclo."

### Passo 8 — Subir o retorno no MedPag (2 min)

1. Aba do Thiago → lote aprovado → **Subir retorno do banco**
2. Faça upload do `.ret`
3. Sistema concilia automaticamente

> **Comentário:**
> "Olha agora: o lote mostra 39 PAGO e 3 NAO_PAGO. Em cada não-pago,
> o motivo: 1 saldo insuficiente, 1 conta inválida, 1 conta inexistente.
> Nenhum trabalho manual de cruzar planilha. O hospital pode entrar no
> portal dele agora e ver tudo."

### Passo 9 — Auditoria (1 min)

1. Mostre o registro de auditoria do lote:
   - Quem aprovou (Thiago)
   - Quando (timestamp)
   - Valor exato
   - Hash do arquivo gerado

> **Comentário:**
> "Auditoria completa. Se algum médico questionar, você tem prova
> imutável: quando, quanto, quem aprovou, qual arquivo foi gerado."

### Passo 10 — Fechamento (2 min)

> **Frase de fechamento:**
> "Tempo total dessa operação: ~15 min com 45 médicos.
> Hoje você gasta quanto tempo nisso? [escutar Thiago]
> Em escala: 5 hospitais como esse por mês = ~25 lotes,
> de horas pra minutos."

Pergunte:
- "Você consegue ver isso rodando na sua operação hoje?"
- "Quais ajustes faltam pra ficar 100% do jeito que você precisa?"
- "Quer fazer um piloto de 30 dias com 1 hospital real?"

## Perguntas comuns e respostas

**P: Funciona offline?**
R: Não. É web. Mas o internet banking da Unicred também é. Mesmo cenário.

**P: E se a planilha do hospital vier diferente?**
R: O sistema tenta mapear colunas automaticamente (CPF, Documento, Beneficiário,
Nome do Prestador, etc). Se não conseguir, na Fase 2 a gente salva
o mapeamento manual do cliente e ele vira automático nas próximas.

**P: E se o hospital não tem conta na Unicred?**
R: Hoje o MVP é Unicred-only. Multi-banco entra na Fase 2 (Itaú, BB, Bradesco, Sicredi).

**P: Quem paga as taxas do banco?**
R: O hospital paga, porque a conta debitada é dele. O Thiago só presta serviço.

**P: E o LGPD?**
R: CPFs e contas são criptografados em repouso (AES-256). Logs nunca exibem
dado completo (só mascarado). Auditoria de 10 anos.

**P: Quanto vai me cobrar?**
R: Modelo de cobrança ainda em definição. Ideias:
- Mensalidade por hospital (R$ 800-3.000/mês conforme volume)
- Ou taxa por pagamento processado (R$ 0,50-2,00 por linha)
- Ou misto (mensalidade base + variável por volume)

## Dicas de apresentação

- **Tenha um backup local rodando** caso a internet caia ou o Render demore
- **Não fique perdendo tempo no terminal** durante a demo — pré-baixe o `.rem`
  e tenha o comando do simulador pronto pra colar
- **Conte uma história** ("Imagina que é dia 28, o Santa Casa te mandou a planilha
  às 16h de uma sexta...")
- **Deixe a planilha de erros plantados servir** — quando aparecer amarelo/vermelho,
  comemore visualmente: "Olha aqui! O sistema pegou! Sem ele, esses 3 médicos
  iam ficar sem receber."
- **Termine com pergunta aberta**, não com pitch de venda
