# CNAB 240 — Layout Unicred (código 136)

> Este documento descreve o layout do arquivo CNAB 240 esperado pela Unicred
> para pagamentos em lote (folha de pagamento e pagamento a fornecedores PJ).
>
> Referência oficial: manual do Banco Cooperativo do Brasil (Unicred) disponível
> em https://www.unicred.com.br/ (área do cliente PJ).
>
> **IMPORTANTE:** o layout abaixo é a descrição genérica do padrão FEBRABAN
> versão 10.7. Antes de gerar arquivo real, confirmar com a Unicred o layout
> específico em vigor (versões podem mudar).

---

## Estrutura geral

Um arquivo CNAB 240 é composto por linhas de 240 caracteres cada (sem CR/LF
até o final). A estrutura tem registros aninhados:

```
ARQUIVO
├── Header de Arquivo (registro tipo 0)
├── LOTE 1
│   ├── Header de Lote (registro tipo 1)
│   ├── Detalhe Segmento A (registro tipo 3) — dados do pagamento
│   ├── Detalhe Segmento B (registro tipo 3) — endereço/informações complementares
│   ├── ... (repete A+B pra cada pagamento)
│   └── Trailer de Lote (registro tipo 5)
├── LOTE 2
│   └── ...
└── Trailer de Arquivo (registro tipo 9)
```

Para o MVP do MedPag, geramos **um lote por arquivo** (um lote MedPag = um lote CNAB).

---

## Tipos de pagamento suportados (campo Forma de Lançamento)

Código | Tipo
-------|-----
01 | Crédito em Conta Corrente
03 | DOC
41 | TED
45 | PIX
05 | Crédito em Conta Poupança

Para MedPag MVP usamos **01** (crédito em conta corrente, mesmo banco) e
**41** (TED entre bancos diferentes).

---

## Registro 0 — Header de Arquivo (240 chars)

Posição | Tamanho | Campo | Valor MedPag
--------|---------|-------|-------------
001-003 | 3 | Código do banco | `136` (Unicred)
004-007 | 4 | Código do lote | `0000`
008-008 | 1 | Tipo de registro | `0`
009-017 | 9 | Filler (brancos) | espaços
018-018 | 1 | Tipo de inscrição empresa | `1` (CPF) ou `2` (CNPJ)
019-032 | 14 | CNPJ/CPF da empresa pagadora | CNPJ do Thiago
033-052 | 20 | Código do convênio | fornecido pela Unicred
053-057 | 5 | Agência | agência da Unicred do Thiago
058-058 | 1 | DV da agência | dígito verificador
059-070 | 12 | Conta corrente | conta da empresa
071-071 | 1 | DV da conta | dígito
072-072 | 1 | DV da agência+conta | dígito combinado
073-102 | 30 | Nome da empresa | razão social (maiúsculas, sem acentos)
103-132 | 30 | Nome do banco | `UNICRED`
133-142 | 10 | Filler | espaços
143-143 | 1 | Código de remessa/retorno | `1` (remessa) ou `2` (retorno)
144-151 | 8 | Data de geração | DDMMAAAA
152-157 | 6 | Hora de geração | HHMMSS
158-163 | 6 | Número sequencial do arquivo | incremental
164-166 | 3 | Versão do layout | `103` ou conforme manual atual
167-171 | 5 | Densidade | `01600`
172-191 | 20 | Uso reservado banco | espaços
192-211 | 20 | Uso reservado empresa | espaços
212-240 | 29 | Filler | espaços

---

## Registro 1 — Header de Lote (240 chars)

Posição | Tamanho | Campo | Valor MedPag
--------|---------|-------|-------------
001-003 | 3 | Código do banco | `136`
004-007 | 4 | Código do lote | sequencial dentro do arquivo, ex `0001`
008-008 | 1 | Tipo de registro | `1`
009-009 | 1 | Tipo da operação | `C` (crédito)
010-011 | 2 | Tipo do serviço | `30` (folha de pagamento) ou `98` (diversos)
012-013 | 2 | Forma de lançamento | `01` (CC), `41` (TED), `45` (PIX)
014-016 | 3 | Versão do layout do lote | `046`
017-017 | 1 | Filler | espaço
018-018 | 1 | Tipo de inscrição empresa | `1` ou `2`
019-032 | 14 | CNPJ/CPF empresa | mesmo do header de arquivo
033-052 | 20 | Código do convênio | mesmo do header
053-072 | 20 | Conta+agência+DV | mesmos do header
073-102 | 30 | Nome da empresa | mesmo do header
103-142 | 40 | Mensagem 1 (livre) | ex: `FOLHA JUNHO/2026`
143-172 | 30 | Endereço da empresa | logradouro
173-177 | 5 | Número | número do endereço
178-192 | 15 | Complemento | apto/sala
193-212 | 20 | Cidade | nome da cidade
213-220 | 8 | CEP | apenas dígitos
221-222 | 2 | UF | sigla
223-230 | 8 | Filler | espaços
231-240 | 10 | Códigos de retorno | espaços (só usado no retorno)

---

## Registro 3 — Detalhe Segmento A (240 chars)

**O pagamento em si.** Um segmento A por pagamento.

Posição | Tamanho | Campo | Valor MedPag
--------|---------|-------|-------------
001-003 | 3 | Código do banco | `136`
004-007 | 4 | Código do lote | mesmo do header do lote
008-008 | 1 | Tipo de registro | `3`
009-013 | 5 | Número sequencial dentro do lote | incremental (00001, 00002...)
014-014 | 1 | Código segmento | `A`
015-015 | 1 | Tipo de movimento | `0` (inclusão), `9` (exclusão)
016-017 | 2 | Código instrução | `00`
018-020 | 3 | Câmara | `018` (TED) ou `000` (CC)
021-023 | 3 | Código do banco favorecido | ex: `136` ou `341`
024-028 | 5 | Agência favorecido | dígitos da agência
029-029 | 1 | DV agência | dígito
030-041 | 12 | Conta corrente favorecido | conta
042-042 | 1 | DV conta | dígito
043-043 | 1 | DV agência+conta | dígito combinado
044-073 | 30 | Nome do favorecido | nome do médico (maiúsculas, sem acentos)
074-093 | 20 | Número do documento | identificação livre (ex: ID do pagamento)
094-101 | 8 | Data do pagamento | DDMMAAAA
102-104 | 3 | Tipo da moeda | `BRL`
105-119 | 15 | Quantidade da moeda | `000000000000000` (não usado)
120-134 | 15 | Valor do pagamento | em centavos, 15 dígitos, zero à esquerda
135-149 | 15 | Número do documento atribuído pelo banco | espaços (só retorno)
150-157 | 8 | Data efetiva | espaços (só retorno)
158-172 | 15 | Valor efetivo | espaços (só retorno)
173-212 | 40 | Mensagem 2 | livre, ex `REF JUNHO/2026`
213-214 | 2 | Código finalidade DOC/TED | `10` (crédito em conta)
215-219 | 5 | Filler | espaços
220-224 | 5 | Aviso ao favorecido | `0`
225-230 | 6 | Código ocorrências para retorno | espaços
231-240 | 10 | Filler | espaços

**Cálculo do dígito verificador (DV) agência+conta da Unicred:** consultar
manual específico. Algoritmo varia por banco — Unicred usa módulo 11 padrão
mas com pesos próprios. **Implementar como função separada e testar com
casos reais conhecidos antes de produção.**

---

## Registro 3 — Detalhe Segmento B (240 chars)

Informações complementares do beneficiário (endereço, CPF/CNPJ).

Posição | Tamanho | Campo | Valor MedPag
--------|---------|-------|-------------
001-003 | 3 | Código do banco | `136`
004-007 | 4 | Código do lote | mesmo
008-008 | 1 | Tipo de registro | `3`
009-013 | 5 | Sequencial | incremental, mesmo do A
014-014 | 1 | Código segmento | `B`
015-017 | 3 | Filler | espaços
018-018 | 1 | Tipo de inscrição favorecido | `1` (CPF) ou `2` (CNPJ)
019-032 | 14 | CPF/CNPJ favorecido | dígitos
033-062 | 30 | Endereço | logradouro
063-067 | 5 | Número | número
068-082 | 15 | Complemento | apto
083-097 | 15 | Bairro | bairro
098-117 | 20 | Cidade | cidade
118-125 | 8 | CEP | dígitos
126-127 | 2 | UF | sigla
128-135 | 8 | Data de vencimento | espaços
136-150 | 15 | Valor do documento | espaços
151-165 | 15 | Valor abatimento | espaços
166-180 | 15 | Valor desconto | espaços
181-195 | 15 | Valor mora | espaços
196-210 | 15 | Valor multa | espaços
211-225 | 15 | Código documento favorecido | espaços
226-240 | 15 | Aviso ao favorecido | espaços

---

## Registro 5 — Trailer de Lote (240 chars)

Posição | Tamanho | Campo | Valor MedPag
--------|---------|-------|-------------
001-003 | 3 | Código do banco | `136`
004-007 | 4 | Código do lote | mesmo
008-008 | 1 | Tipo de registro | `5`
009-017 | 9 | Filler | espaços
018-023 | 6 | Quantidade de registros do lote | inclui header A B trailer
024-041 | 18 | Soma valores | total em centavos, 18 dígitos
042-059 | 18 | Soma quantidade moedas | zeros
060-065 | 6 | Número aviso débito | zeros
066-230 | 165 | Filler | espaços
231-240 | 10 | Códigos retorno | espaços

---

## Registro 9 — Trailer de Arquivo (240 chars)

Posição | Tamanho | Campo | Valor MedPag
--------|---------|-------|-------------
001-003 | 3 | Código do banco | `136`
004-007 | 4 | Código do lote | `9999`
008-008 | 1 | Tipo de registro | `9`
009-017 | 9 | Filler | espaços
018-023 | 6 | Quantidade de lotes | total de lotes (1 no MVP)
024-029 | 6 | Quantidade de registros | TOTAL no arquivo (header + lotes + detalhes + trailers)
030-035 | 6 | Quantidade de contas | zeros
036-240 | 205 | Filler | espaços

---

## Regras de formatação

- **Numéricos:** zero à esquerda, alinhado à direita. Ex: valor `R$ 250,00` em campo de 15 = `000000000025000` (centavos)
- **Alfanuméricos:** maiúsculas, sem acentos, alinhado à esquerda, preenchido com espaços. Ex: nome `JOSE DA SILVA` em campo de 30 = `JOSE DA SILVA                 `
- **Datas:** DDMMAAAA. Ex: `21052026`
- **Horas:** HHMMSS. Ex: `143025`
- **Sem CR/LF/separadores internos.** Cada linha tem exatamente 240 chars.
- **Final do arquivo:** uma linha por registro, separados por `\r\n` (CRLF).

---

## Validações antes de gerar o arquivo

Antes de escrever o arquivo, o gerador DEVE verificar:

1. ✅ Todos os pagamentos do lote estão em status APROVADO
2. ✅ Nome do beneficiário tem no máximo 30 chars (truncar com aviso se exceder)
3. ✅ Sem acentos ou caracteres especiais nos campos alfanuméricos
4. ✅ Soma dos valores bate com o totalizador armazenado no Lote
5. ✅ Quantidade de pagamentos bate com o totalizador
6. ✅ Hash SHA-256 do arquivo gerado é registrado em `arquivos_cnab`
7. ✅ Auditoria criada com user_id do aprovador (Thiago)

---

## TODO Cursor — Implementação

A geração do arquivo deve ficar em:

```
app/services/cnab_generator.py
```

Estrutura sugerida:

```python
class CNABGenerator:
    """Gera arquivo CNAB 240 a partir de um Lote aprovado."""

    def __init__(self, lote: Lote, empresa_config: EmpresaConfig):
        self.lote = lote
        self.empresa = empresa_config

    def gerar(self) -> CNABResult:
        """Retorna conteúdo do arquivo + hash + metadata."""
        linhas: list[str] = []
        linhas.append(self._header_arquivo())
        linhas.append(self._header_lote())
        for idx, pagamento in enumerate(self.lote.pagamentos, start=1):
            if pagamento.status != StatusPagamento.APROVADO:
                continue
            linhas.append(self._detalhe_a(pagamento, idx))
            linhas.append(self._detalhe_b(pagamento, idx))
        linhas.append(self._trailer_lote())
        linhas.append(self._trailer_arquivo())

        conteudo = "\r\n".join(linhas) + "\r\n"
        hash_arquivo = hashlib.sha256(conteudo.encode("latin-1")).hexdigest()
        return CNABResult(conteudo=conteudo, hash=hash_arquivo, ...)
```

Testes essenciais:
- Cada registro tem exatamente 240 caracteres
- Soma dos valores no trailer bate com a soma dos detalhes
- Quantidade no trailer bate com quantidade real
- Caracteres alfanuméricos não têm acento
- Datas no formato correto
- DVs calculados corretamente (testar com casos reais conhecidos)
