# Roteiro — Sessão com Thiago (21/05/2026, 10:30 na Auris)

> Abre esse arquivo no celular ou notebook durante a sessão. Marcado pra
> seguir em ordem; cada bloco tem o objetivo e a fala-chave.

---

## Antes de começar (preparação na noite anterior)

- [ ] Está logado na plataforma como `expo@atombrasildigital.com`
      (ADMIN) — testar em janela normal.
- [ ] Maria operadora criada (senha que você anotou).
- [ ] Planilha demo `data/planilhas-demo/planilha-hospital-santa-casa-novembro-2026.xlsx`
      copiada pro pen drive **e** pro Google Drive (backup).
- [ ] Notebook com bateria cheia + cabo + mouse.
- [ ] Pedir pro Thiago abrir a planilha CNAB dele em paralelo
      (a `CNAB - ARQUIVO MESTRE - AURIS.xlsm`) — vamos comparar lado a lado.

---

## Bloco 1 — Mostrar o que já está pronto (10 min)

**Objetivo:** convencer ele que a plataforma já entrega valor hoje, mesmo
sem o gerador CNAB final.

1. **Login como ADMIN** em `med-pay-91t6.vercel.app`.
2. **Mostrar a aba "Empresa"** (sidebar > Administração > Empresa) com a
   tela de cadastro da empresa pagadora **pré-preenchida** com os dados
   da planilha dele.

   > **Fala:** "Thiago, olha que loucura — abri sua planilha CNAB ontem
   > e mapeei a aba INICIO inteira. Os dados da Auris já vêm pré-carregados
   > aqui. Você só clica em salvar."

   - Pedir pra ele confirmar/ajustar os campos e clicar em **Salvar**.
   - Resultado esperado: mensagem verde "Empresa pagadora cadastrada".

3. **Mostrar a aba "Equipe"** (Administração > Equipe).
   - Listar os usuários existentes (Felicio + Maria).
   - Ofereça: "Quer cadastrar seu irmão como Aprovador agora?"
     Se ele topar, ele mesmo cria.

4. **Mostrar o fluxo de upload (modo operador)**:
   - Abrir aba anônima → logar como Maria.
   - Subir a planilha `planilha-hospital-santa-casa-novembro-2026.xlsx`.
   - Aguardar processamento (deve ser ~3 segundos).
   - Mostrar a tela do lote: 38 OK, 2 com sugestão, 5 bloqueados.

   > **Fala:** "Esse é exatamente o tipo de planilha bagunçada que chega
   > pra Maria. Em vez de ela tentar achar erro na mão, o sistema já
   > destacou: aqui tem CPF com erro de digitação, aqui tem valor acima
   > de R$ 50.000 que merece confirmação, aqui tem banco que não existe."

5. **Voltar pra janela admin** → Administração > **Erros**.
   - Mostra o painel com "Prejuízo evitado", ranking de operadores,
     tipos de erro, hospitais.

   > **Fala:** "Esse é o relatório que você e seu irmão vão receber
   > toda segunda. Sabe quem está errando mais? Que tipo de erro?
   > Em qual hospital? E quanto isso teria custado em pagamento errado."

---

## Bloco 2 — Validar o template CNAB dele (15 min)

**Objetivo:** confirmar que entendemos 100% do fluxo dele e alinhar o
gerador CNAB do MedPag com o template Excel atual.

1. Abrir lado a lado a planilha do Thiago e o doc
   `docs/TEMPLATE_THIAGO_AURIS.md` (no notebook).

2. **Validar a aba INICIO**:
   - "Os dados da empresa pagadora estão certos: CNPJ 40.917.845/0001-60,
     conta Unicred Ag 1214-7 / CC 21390-0?"
   - "Esse `código de convênio: 9845046` — é fixo ou muda por contrato?"

3. **Validar a aba AUX (modalidades)**:
   - "Vi que você usa 5 tipos de lote: PIX, TED, transferência interna
     Unicred, boletos e convênios."
   - "Hoje vocês fazem mais PIX ou mais TED?"
   - "Tem casos de boleto e convênio? Quando?"

4. **Validar a aba TED_DOC_TRANS / PIX**:
   - "As colunas que mapeei (FAVORECIDO, IDENTIFICADOR, DT_PGTO, VALOR,
     BANCO, AGÊNCIA, CONTA, etc) batem com o que você espera?"
   - **Pergunta-chave**: "O que é o IDENTIFICADOR? É só uma referência
     interna ou tem regra?"

5. **Aba ERROS**:
   - "Vi que sua planilha já tem aba ERROS. O que cai aí hoje?"
   - "Quero entender pra reproduzir esse tipo de erro na nossa
     validação."

---

## Bloco 3 — Perguntas-chave (10 min)

Anotar tudo em papel ou no celular. Essas respostas viram código no
Sprint 2.

### Operacionais

1. **Sequencial de arquivo CNAB**: qual o número atual em produção?
   (pra MedPag começar do próximo e não dar conflito no banco)

2. **Pasta destino**: hoje você salva em `H:\Meu Drive\FINANCEIRO\LOTE`.
   No MedPag preferir:
   - (A) Download manual do `.txt` pra você arrastar pro internet banking, ou
   - (B) Integração API direta com Unicred?

3. **Token Unicred**: quando você dispara o pagamento, o token chega como?
   - SMS pro seu celular?
   - Email?
   - App Unicred?
   - Token físico?

   Pergunta de follow-up: "Posso testar arrastar um CNAB que o MedPag
   gera no seu internet banking semana que vem? Sem clicar em confirmar,
   só pra ver se o banco aceita o formato."

### Técnicas

4. **Modalidade default**: se o médico tem chave PIX cadastrada,
   pago como PIX (mais barato e rápido). Se não tem, pago TED.
   Concorda?

5. **Dígito Bradesco**: sua planilha tem uma coluna especial pro
   DV do Bradesco. Qual a regra?

6. **CPF/CNPJ pagador**: o `40.917.845/0001-60` é da Auris ou de outra
   das empresas suas? Tem mais de uma empresa pagadora? (caso sim,
   precisamos suportar multi-empresa no cadastro)

### Comerciais (pra fechar como sócio)

7. **Volume mensal**: quanto sai pela conta Unicred por mês?
   - Em R$
   - Em quantidade de pagamentos
   - Em quantidade de hospitais

8. **Taxa de erro estimada hoje**: dos pagamentos que vão pro banco,
   quantos voltam? Quantos viram duplicidade? Qual % do volume isso
   representa em prejuízo anual?

9. **Quanto vocês gastariam pra economizar isso?** (mensalidade que
   ele acharia justa)

---

## Bloco 4 — Demo da "feature mais nova" (5 min)

**Objetivo:** mostrar uma feature que ainda não existia ontem, pra ele
sentir velocidade de execução.

1. Voltar pra tela do lote da Santa Casa.
2. Mostrar a coluna **"Envio"** (PIX / TED / Interna):
   > **Fala:** "Cada pagamento o sistema já decide se vai por PIX ou TED,
   > igual sua planilha. Lá você preenche em duas abas separadas; aqui
   > a gente vê tudo junto e o gerador CNAB depois separa em dois lotes
   > automaticamente."

3. Mostrar o badge azul (TED) vs verde (PIX) vs marrom (Interna) e
   explicar que isso espelha o `tipo_servico + forma_lanc` da aba AUX
   da planilha dele.

---

## Bloco 5 — Próximos 7 dias (5 min)

Alinhar prioridades pra entregar até a próxima sessão:

1. **Sprint 2 — gerador CNAB 240 real**: até `01/06`, MedPag gera um
   arquivo `.txt` idêntico ao da planilha dele. Vamos rodar lado a lado
   e comparar os bytes.

2. **Sprint 2 — adapter Unicred API**: se ele topar o piloto automático,
   eu começo a estudar a API Unicred.

3. **Cadastro de beneficiários com chave PIX**: assim que tivermos isso,
   os pagamentos viram PIX automático (mais barato pra Auris).

---

## Bloco 6 — Combinar próximo passo (2 min)

- Quando é a próxima reunião?
- Posso vir aqui na empresa de novo ou faz por chamada?
- Você tem uma planilha real (anonimizada) de novembro pra eu rodar
  no MedPag e te mandar o `.txt` resultante pra você comparar com o
  que sua planilha CNAB gerou?

---

## Lista do que coletar pra trazer pra casa

- [ ] Sequencial de arquivo atual: _____________
- [ ] Volume mensal Unicred (R$): _____________
- [ ] Quantidade pagamentos/mês: _____________
- [ ] Quantidade hospitais ativos: _____________
- [ ] Taxa de erro estimada: _____________
- [ ] Mensalidade aceitável: R$ _____________
- [ ] Regra do dígito Bradesco: _____________
- [ ] Planilha real anonimizada (.xlsx): _____________
- [ ] Aba ERROS da planilha dele com exemplos: _____________
- [ ] Conta para conferência: a Auris ou tem outra empresa pagadora?
      Resposta: _____________

---

## Em caso de problema técnico durante a demo (Plan B)

- Se o Render estiver fora do ar (raro): abrir `localhost` no
  notebook via `docker compose up -d` (testar antes!).
- Se travar a planilha: usar a `planilha-clinica-vida-nova-novembro-2026.xlsx`
  (segundo backup).
- Se ele perguntar algo que eu não sei: anotar e responder por whatsapp
  no fim do dia.

---

## Frase pra fechar a sessão

> "Thiago, hoje a gente alinhou a base. Vou voltar pra casa, implementar
> o gerador CNAB real seguindo seu template — quando você for arrastar
> o `.txt` que sai do MedPag no internet banking da Unicred, ele vai
> ser **idêntico** ao que sua planilha gera hoje, com a vantagem de
> ter passado pelos validadores antes. Combinamos pra sexta?"
