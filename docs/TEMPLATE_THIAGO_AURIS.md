# Template CNAB do Thiago — "CNAB Arquivo Mestre Auris.xlsm"

> Engenharia reversa do arquivo `CNAB - ARQUIVO MESTRE - AURIS.xlsm` enviado
> pelo Thiago em 20/05/2026. É o **template oficial** que ele usa hoje pra
> gerar o CNAB que sobe na conta Unicred. Base pra alinhar o gerador CNAB
> do MedPag 1:1 com o que o banco aceita do Thiago.
>
> Arquivo local: `data/thiago/cnab-mestre-auris.xlsm`

---

## Empresa pagadora (aba INICIO)

Dados fixos da conta pagadora — vão no header de arquivo do CNAB:

| Campo | Valor |
|---|---|
| Nome cooperado | UNICRED DO BRASIL |
| Banco | 136 |
| Agência (c/ dígito) | 1214-7 |
| Conta (c/ dígito) | 21390-0 |
| CNPJ pagador | 40.917.845/0001-60 |
| Sequencial arquivo | (incrementa a cada geração) |
| Endereço | Av das Américas, 11365, Sala 340 — Rio de Janeiro/RJ |
| CEP | 22793-082 |
| Tipo conta | CORRENTE |
| Pasta destino CNAB | `H:\Meu Drive\FINANCEIRO\LOTE` (Google Drive sincronizado) |
| Validar dados | NÃO (a planilha tem macro de validação opcional) |

> **Tradução pro MedPag**: precisamos criar uma tela
> `/app/admin/empresa-pagadora` pra cadastrar exatamente esses campos.
> Hoje estão hardcoded ou faltando.

---

## 5 modalidades de lote (aba AUX)

A planilha do Thiago gera **um arquivo CNAB que pode conter até 5 lotes**,
um por modalidade. Cada modalidade tem o par `tipo_servico` + `forma_lanc`
que vai no Header de Lote (registro tipo 1) do CNAB 240:

| Aba | Modalidade | tipo_servico | forma_lanc | Quando usar |
|---|---|---|---|---|
| PIX | Pagamento PIX | 98 | 45 | Beneficiário com chave PIX ou conta destino |
| TED_DOC_TRANS | TED outro banco | 30 | 01 | Beneficiário em banco diferente da Unicred |
| (TRANS) | Transferência interna | 98 | 41 | Beneficiário também na Unicred |
| BOLETOS | Pagamento de boleto | 98 | 31 | Pagar boleto cobrança |
| CONVENIOS | Convênios (água/luz/...) | 22 | 11 | Tributos e convênios |

> **Áudio do Thiago**: "*A única coisa que a gente mexe é na aba TED, quando
> faz pagamento em TED, ou na aba PIX, quando a gente faz pagamento Pix. E
> só preenche um ou outro, não dá pra ser Pix e TED.*"
>
> Tradução: cada **pagamento individual** é PIX ou TED, nunca os dois.
> Mas no mesmo arquivo CNAB pode ter um lote PIX **e** um lote TED, em
> paralelo. A regra do "ou um ou outro" é por linha de beneficiário.

---

## Aba TED_DOC_TRANS — colunas

12 colunas obrigatórias por linha:

| # | Coluna | Significado |
|---|---|---|
| 1 | FAVORECIDO | Nome completo do médico/prestador |
| 2 | IDENTIFICADOR | Referência interna (opcional, vai no segmento B) |
| 3 | DT_PGTO | Data do pagamento (DD/MM/AAAA) |
| 4 | TIPO_FAVORECIDO | CPF ou CNPJ (vira código 1 ou 2 no CNAB) |
| 5 | DOCUMENTO | Número do CPF (11) ou CNPJ (14) |
| 6 | VALOR | Em reais (vira centavos no CNAB) |
| 7 | BANCO | Código FEBRABAN destino (3 dígitos) |
| 8 | AGÊNCIA | Agência destino (sem dígito ou com tração) |
| 9 | CONTA | Conta destino (com dígito, formato `12345-6`) |
| 10 | VALIDAÇÃO | Auto-validação da macro (somente exibição) |
| 11 | DÍGITO BRADESCO | Tratamento especial pro Bradesco (237) |
| 12 | CNPJ | Campo livre (provável agrupador) |

---

## Aba PIX — colunas

12 colunas obrigatórias por linha:

| # | Coluna | Significado |
|---|---|---|
| 1 | FAVORECIDO | Nome completo |
| 2 | IDENTIFICADOR | Referência interna (vai como TX ID no CNAB) |
| 3 | DT_PGTO | Data do pagamento |
| 4 | TIPO_FAVORECIDO | CPF ou CNPJ (1/2) |
| 5 | DOCUMENTO | Número CPF/CNPJ |
| 6 | VALOR | Em reais |
| 7 | BANCO | Código FEBRABAN destino |
| 8 | AGÊNCIA | Agência destino (se TIPO = AGÊNCIA E CONTA) |
| 9 | CONTA | Conta destino |
| 10 | TIPO | `CHAVE` ou `AGÊNCIA E CONTA` |
| 11 | TIPO_CONTA | CORRENTE / PAGAMENTO / POUPANÇA (01/02/03) |
| 12 | CHAVE | Chave PIX (se TIPO = CHAVE): CPF, e-mail, telefone, EVP |

---

## Estrutura do CNAB gerado (aba CNAB)

A macro VBA da planilha gera o arquivo `.rem` (CNAB 240). Exemplo da aba
CNAB do template (de um teste anterior do Thiago):

```
13600000         240917845000160 ...   01214700 ...     # Header Arquivo (tipo 0)
13600011C9845046 240917845000160 ...   01214700 ...     # Header Lote PIX (tipo 1, lote 001)
1360001300001A0000093410838900000000114383 MARCIA L... # Seg A, pagto 1 (R$ 1.143,83)
1360001300002B05 100086968521768TX ID                  # Seg B, pagto 1
1360001300003A0000093410489500000000283309 EMMYLI ...  # Seg A, pagto 2 (R$ 2.833,09)
1360001300004B05 100013736594755TX ID                  # Seg B, pagto 2
1360001300005A0000090330228400000010488403 JULIANA ... # Seg A, pagto 3 (R$ 104.884,03)
1360001300006B05 100010820201766TX ID                  # Seg B, pagto 3
13600015         0000070000000000010347490000000000... # Trailer Lote (tipo 5)
13699999         000001000009000001                    # Trailer Arquivo (tipo 9)
```

Padrão de nome do arquivo gerado: `136CNAB240<seq>20260<seq>00000XX.txt`
(ex: `136CNAB2403003202600213900000054.txt`).

---

## Tabelas auxiliares importantes

### TIPO_PESSOA
- CPF → 1
- CNPJ → 2

### TIPO_CONTA (PIX)
- CORRENTE → 01
- PAGAMENTO → 02
- POUPANÇA → 03

### TIPO_PIX
- AGÊNCIA E CONTA (sem chave)
- CHAVE (com chave PIX)

### ISPB
A aba `ISPB_BANCOS` tem ~353 bancos com seus códigos ISPB
(Identificador do Sistema de Pagamentos Brasileiros, exigido em
operações PIX/SPB). A aba `ISPB_UNICRED` lista ~404 cooperativas
Unicred individualmente.

---

## Roadmap MedPag derivado deste template

### Sprint 1 (hoje/amanhã — pra demo viver)
- [x] Aceitar bancos diferentes da Unicred (Itaú, Bradesco, Santander,
      BB, Caixa, ...) — fixado em `backend/app/validators/banco.py`.
- [ ] Tela `/app/admin/empresa-pagadora` para o Thiago cadastrar os
      dados da Unicred (CNPJ, agência, conta, sequencial corrente).
- [ ] Permitir que cada pagamento seja marcado como PIX ou TED
      (default por regra: se tem chave PIX → PIX, senão → TED).

### Sprint 2 (gerador CNAB real)
- [ ] Refactor do gerador CNAB para padrão FEBRABAN 10.7, com:
  - [ ] Header de Arquivo (tipo 0) com dados da `empresa_pagadora`.
  - [ ] Multi-lote no mesmo arquivo (PIX + TED juntos).
  - [ ] Segmento A + B por pagamento (com TX ID no B pro PIX).
  - [ ] Trailers de lote e de arquivo com somatórios corretos.
- [ ] Sequencial de arquivo persistido em banco (incrementa a cada
      geração, igual o `Sequencial Arquivo` da planilha do Thiago).
- [ ] Geração do nome do arquivo seguindo o padrão Unicred
      (`136CNAB240<seq>...txt`).
- [ ] Endpoint de download `.txt` (em vez de `.rem`, alinhado com o
      que a planilha do Thiago produz hoje).

### Sprint 3 (paridade com a macro Unicred)
- [ ] Suporte às outras modalidades: TRANS (intra-Unicred),
      BOLETOS, CONVENIOS.
- [ ] Validação automática de ISPB (usar a aba ISPB_BANCOS importada
      pra base do MedPag).
- [ ] Validação especial do dígito Bradesco (a planilha do Thiago
      tem coluna dedicada — provavelmente tratamento de DV diferente).

---

## Decisões abertas (alinhar com o Thiago amanhã)

1. **Onde o Thiago quer colar o CNAB final**: hoje a planilha salva em
   `H:\Meu Drive\FINANCEIRO\LOTE`. Vamos manter o download manual ou
   fazer envio direto na API Unicred?
2. **Sequencial de arquivo**: a planilha começa em `00` e a regra de
   incremento é manual. No MedPag vamos automatizar — qual o valor
   atual em produção pra não dar conflito?
3. **Modalidade default por beneficiário**: a planilha do hospital não
   diz se é PIX ou TED. Sugestão: se o beneficiário tem chave PIX
   cadastrada → PIX, senão → TED. Confirmar com o Thiago.
4. **Dígito Bradesco**: descobrir qual a regra exata (tem cálculo
   próprio do Bradesco para o DV da conta).
