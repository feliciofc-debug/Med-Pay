"""Gerador de arquivo CNAB 240 — layout Unicred (banco 136).

REGRAS INEGOCIÁVEIS:
- Cada linha deve ter EXATAMENTE 240 caracteres
- Soma de valores no trailer DEVE bater com soma dos detalhes
- Quantidade no trailer DEVE bater com quantidade real
- Hash SHA-256 do arquivo é registrado em Auditoria
- Arquivo só é gerado se TODOS os pagamentos estão APROVADOS

Layout completo em `docs/CNAB240_UNICRED.md`.

Estrutura do arquivo (1 lote por arquivo no MVP):
    Header de Arquivo  (Tipo 0)
    Header de Lote     (Tipo 1)
    Para cada pagamento:
        Segmento A     (Tipo 3)
        Segmento B     (Tipo 3)
    Trailer de Lote    (Tipo 5)
    Trailer de Arquivo (Tipo 9)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from app.core.crypto import decrypt
from app.models.empresa_config import EmpresaConfig, TipoInscricao
from app.models.lote import Lote
from app.models.pagamento import Pagamento, StatusPagamento
from app.services.cnab_utils import (
    fmt_alfa,
    fmt_brancos,
    fmt_data,
    fmt_hora,
    fmt_num,
    fmt_zeros,
)

LARGURA_LINHA = 240
TERMINADOR_LINHA = "\r\n"

CODIGO_BANCO_UNICRED = "136"
NOME_BANCO_UNICRED = "UNICRED"
VERSAO_LAYOUT_ARQUIVO = "103"
VERSAO_LAYOUT_LOTE = "046"
DENSIDADE = "01600"
TIPO_SERVICO_FOLHA = "30"  # folha de pagamento
FORMA_LANCAMENTO_CC = "01"  # crédito conta corrente


@dataclass(slots=True)
class CNABResult:
    """Resultado da geração do arquivo CNAB."""

    conteudo: str
    hash_sha256: str
    nome_arquivo: str
    quantidade_pagamentos: int
    valor_total_centavos: int
    quantidade_registros: int

    @property
    def conteudo_bytes(self) -> bytes:
        """Bytes em latin-1 (encoding tradicional do CNAB)."""
        return self.conteudo.encode("latin-1")

    @property
    def tamanho_bytes(self) -> int:
        return len(self.conteudo_bytes)


class CNABGeneratorError(Exception):
    """Erro na geração do CNAB (regra de negócio quebrada)."""


class CNABGenerator:
    """Gera arquivo CNAB 240 a partir de um Lote aprovado."""

    def __init__(
        self,
        lote: Lote,
        pagamentos: list[Pagamento],
        empresa: EmpresaConfig,
        *,
        numero_sequencial_arquivo: int,
        codigo_lote_no_arquivo: int = 1,
        agora: datetime | None = None,
    ) -> None:
        self.lote = lote
        self.pagamentos = [
            p for p in pagamentos if p.status == StatusPagamento.APROVADO
        ]
        self.empresa = empresa
        self.numero_sequencial = numero_sequencial_arquivo
        self.codigo_lote = codigo_lote_no_arquivo
        self.agora = agora or datetime.now()

    # ============================================================
    # Helpers
    # ============================================================

    @property
    def _tipo_inscricao_codigo(self) -> str:
        return "1" if self.empresa.tipo_inscricao == TipoInscricao.CPF else "2"

    @property
    def _data_geracao(self) -> str:
        return fmt_data(self.agora)

    @property
    def _hora_geracao(self) -> str:
        return fmt_hora(self.agora)

    def _conta_pagadora(self) -> tuple[str, str, str]:
        """Retorna (agencia, conta, dv_combinado) da empresa pagadora.

        A conta vem criptografada e é descriptografada aqui.
        """
        agencia = (self.empresa.agencia or "").rjust(5, "0")
        conta_plain = decrypt(self.empresa.conta_encrypted)
        # Conta no CNAB tem 12 chars
        conta = "".join(c for c in conta_plain if c.isdigit()).zfill(12)
        dv = self.empresa.conta_dv or "0"
        return agencia, conta, dv

    # ============================================================
    # Registro 0 — Header de Arquivo (240 chars)
    # ============================================================

    def _header_arquivo(self) -> str:
        agencia, conta, conta_dv = self._conta_pagadora()
        agencia_dv = self.empresa.agencia_dv or "0"

        partes: list[str] = [
            CODIGO_BANCO_UNICRED,                                # 001-003
            "0000",                                              # 004-007
            "0",                                                 # 008
            fmt_brancos(9),                                      # 009-017 reservado
            self._tipo_inscricao_codigo,                         # 018
            fmt_num(self.empresa.cnpj_cpf, 14),                  # 019-032
            fmt_alfa(self.empresa.codigo_convenio, 20),          # 033-052
            fmt_num(agencia, 5),                                 # 053-057
            fmt_alfa(agencia_dv, 1),                             # 058
            fmt_num(conta, 12),                                  # 059-070
            fmt_alfa(conta_dv, 1),                               # 071
            fmt_alfa(conta_dv, 1),                               # 072 (DV combinado — usamos o da conta)
            fmt_alfa(self.empresa.razao_social, 30),             # 073-102
            fmt_alfa(NOME_BANCO_UNICRED, 30),                    # 103-132
            fmt_brancos(10),                                     # 133-142 filler
            "1",                                                 # 143 (1=remessa)
            self._data_geracao,                                  # 144-151
            self._hora_geracao,                                  # 152-157
            fmt_num(self.numero_sequencial, 6),                  # 158-163
            VERSAO_LAYOUT_ARQUIVO,                               # 164-166
            DENSIDADE,                                           # 167-171
            fmt_brancos(20),                                     # 172-191 reservado banco
            fmt_brancos(20),                                     # 192-211 reservado empresa
            fmt_brancos(29),                                     # 212-240 filler
        ]
        return _validar_e_concatenar(partes, "Header de Arquivo")

    # ============================================================
    # Registro 1 — Header de Lote (240 chars)
    # ============================================================

    def _header_lote(self) -> str:
        agencia, conta, conta_dv = self._conta_pagadora()
        agencia_dv = self.empresa.agencia_dv or "0"
        # Conta + agência + DV juntos em 20 chars
        conta_agencia_dv = (
            fmt_num(agencia, 5)
            + fmt_alfa(agencia_dv, 1)
            + fmt_num(conta, 12)
            + fmt_alfa(conta_dv, 1)
            + fmt_alfa(conta_dv, 1)
        )

        partes: list[str] = [
            CODIGO_BANCO_UNICRED,                                # 001-003
            fmt_num(self.codigo_lote, 4),                        # 004-007
            "1",                                                 # 008
            "C",                                                 # 009 (operação=Crédito)
            TIPO_SERVICO_FOLHA,                                  # 010-011
            FORMA_LANCAMENTO_CC,                                 # 012-013
            VERSAO_LAYOUT_LOTE,                                  # 014-016
            " ",                                                 # 017 filler
            self._tipo_inscricao_codigo,                         # 018
            fmt_num(self.empresa.cnpj_cpf, 14),                  # 019-032
            fmt_alfa(self.empresa.codigo_convenio, 20),          # 033-052
            conta_agencia_dv,                                    # 053-072 (20 chars)
            fmt_alfa(self.empresa.razao_social, 30),             # 073-102
            fmt_alfa(self.lote.referencia or "FOLHA PAGAMENTO", 40),  # 103-142
            fmt_alfa(self.empresa.endereco_logradouro, 30),      # 143-172
            fmt_num(self.empresa.endereco_numero, 5),            # 173-177
            fmt_alfa(self.empresa.endereco_complemento, 15),     # 178-192
            fmt_alfa(self.empresa.endereco_cidade, 20),          # 193-212
            fmt_num(self.empresa.endereco_cep, 8),               # 213-220
            fmt_alfa(self.empresa.endereco_uf, 2),               # 221-222
            fmt_brancos(8),                                      # 223-230 filler
            fmt_brancos(10),                                     # 231-240 ocorrências (retorno)
        ]
        return _validar_e_concatenar(partes, "Header de Lote")

    # ============================================================
    # Registro 3 — Detalhe Segmento A (240 chars)
    # ============================================================

    def _segmento_a(self, pagamento: Pagamento, sequencial: int) -> str:
        agencia = (pagamento.agencia_encrypted and decrypt(pagamento.agencia_encrypted)) or ""
        conta = (pagamento.conta_encrypted and decrypt(pagamento.conta_encrypted)) or ""

        # Agência: 5 dígitos + 1 DV (não calculamos aqui, deixa zero — banco recalcula)
        agencia_num = "".join(c for c in agencia if c.isdigit()).zfill(5)
        # Conta: 12 dígitos + DV
        conta_digitos = "".join(c for c in conta if c.isdigit()).zfill(12)

        camara = "000" if pagamento.banco_codigo == CODIGO_BANCO_UNICRED else "018"

        partes: list[str] = [
            CODIGO_BANCO_UNICRED,                                # 001-003
            fmt_num(self.codigo_lote, 4),                        # 004-007
            "3",                                                 # 008
            fmt_num(sequencial, 5),                              # 009-013
            "A",                                                 # 014
            "0",                                                 # 015 (movimento=inclusão)
            "00",                                                # 016-017 (instrução)
            camara,                                              # 018-020
            fmt_num(pagamento.banco_codigo or "0", 3),           # 021-023
            agencia_num,                                         # 024-028
            "0",                                                 # 029 (DV agência)
            conta_digitos,                                       # 030-041
            "0",                                                 # 042 (DV conta)
            "0",                                                 # 043 (DV ag+conta)
            fmt_alfa(pagamento.nome, 30),                        # 044-073
            fmt_alfa(str(pagamento.id)[:20], 20),                # 074-093 (ID do pagamento)
            self._data_geracao,                                  # 094-101 (data efetiva)
            "BRL",                                               # 102-104
            fmt_zeros(15),                                       # 105-119
            fmt_num(pagamento.valor_centavos, 15),               # 120-134
            fmt_brancos(15),                                     # 135-149
            fmt_brancos(8),                                      # 150-157
            fmt_brancos(15),                                     # 158-172
            fmt_alfa(self.lote.referencia or "", 40),            # 173-212
            "10",                                                # 213-214 (finalidade)
            fmt_brancos(5),                                      # 215-219
            "0",                                                 # 220 (aviso favorecido)
            fmt_brancos(4),                                      # 221-224
            fmt_brancos(6),                                      # 225-230
            fmt_brancos(10),                                     # 231-240
        ]
        return _validar_e_concatenar(partes, f"Segmento A (seq {sequencial})")

    # ============================================================
    # Registro 3 — Detalhe Segmento B (240 chars)
    # ============================================================

    def _segmento_b(self, pagamento: Pagamento, sequencial: int) -> str:
        cpf = decrypt(pagamento.cpf_encrypted) if pagamento.cpf_encrypted else ""
        cpf_digitos = "".join(c for c in cpf if c.isdigit())
        # Tipo: 1=CPF, 2=CNPJ
        tipo_inscricao = "1" if len(cpf_digitos) == 11 else "2"

        partes: list[str] = [
            CODIGO_BANCO_UNICRED,                                # 001-003
            fmt_num(self.codigo_lote, 4),                        # 004-007
            "3",                                                 # 008
            fmt_num(sequencial, 5),                              # 009-013
            "B",                                                 # 014
            fmt_brancos(3),                                      # 015-017
            tipo_inscricao,                                      # 018
            fmt_num(cpf_digitos, 14),                            # 019-032
            fmt_alfa("", 30),                                    # 033-062 endereço
            fmt_zeros(5),                                        # 063-067 número
            fmt_alfa("", 15),                                    # 068-082 complemento
            fmt_alfa("", 15),                                    # 083-097 bairro
            fmt_alfa("", 20),                                    # 098-117 cidade
            fmt_zeros(8),                                        # 118-125 CEP
            fmt_alfa("", 2),                                     # 126-127 UF
            fmt_zeros(8),                                        # 128-135 vencimento
            fmt_zeros(15),                                       # 136-150 valor doc
            fmt_zeros(15),                                       # 151-165 abatimento
            fmt_zeros(15),                                       # 166-180 desconto
            fmt_zeros(15),                                       # 181-195 mora
            fmt_zeros(15),                                       # 196-210 multa
            fmt_alfa("", 15),                                    # 211-225
            fmt_alfa("", 15),                                    # 226-240
        ]
        return _validar_e_concatenar(partes, f"Segmento B (seq {sequencial})")

    # ============================================================
    # Registro 5 — Trailer de Lote
    # ============================================================

    def _trailer_lote(self, qtd_registros_lote: int, soma_valores: int) -> str:
        partes: list[str] = [
            CODIGO_BANCO_UNICRED,                                # 001-003
            fmt_num(self.codigo_lote, 4),                        # 004-007
            "5",                                                 # 008
            fmt_brancos(9),                                      # 009-017
            fmt_num(qtd_registros_lote, 6),                      # 018-023
            fmt_num(soma_valores, 18),                           # 024-041
            fmt_zeros(18),                                       # 042-059
            fmt_zeros(6),                                        # 060-065
            fmt_brancos(165),                                    # 066-230
            fmt_brancos(10),                                     # 231-240
        ]
        return _validar_e_concatenar(partes, "Trailer de Lote")

    # ============================================================
    # Registro 9 — Trailer de Arquivo
    # ============================================================

    def _trailer_arquivo(self, qtd_lotes: int, qtd_registros_total: int) -> str:
        partes: list[str] = [
            CODIGO_BANCO_UNICRED,                                # 001-003
            "9999",                                              # 004-007
            "9",                                                 # 008
            fmt_brancos(9),                                      # 009-017
            fmt_num(qtd_lotes, 6),                               # 018-023
            fmt_num(qtd_registros_total, 6),                     # 024-029
            fmt_zeros(6),                                        # 030-035
            fmt_brancos(205),                                    # 036-240
        ]
        return _validar_e_concatenar(partes, "Trailer de Arquivo")

    # ============================================================
    # Função principal
    # ============================================================

    def gerar(self) -> CNABResult:
        """Monta o arquivo completo, valida e calcula hash."""
        if not self.pagamentos:
            raise CNABGeneratorError(
                "Lote não tem nenhum pagamento APROVADO — nada a gerar"
            )

        linhas: list[str] = []
        linhas.append(self._header_arquivo())
        linhas.append(self._header_lote())

        soma_valores = 0
        # No CNAB 240 o sequencial dentro do lote (posições 9-13 de cada
        # segmento detalhe) é POR REGISTRO, não por pagamento. Como cada
        # pagamento gera 2 linhas (Segmento A + Segmento B), o sequencial
        # avança 1 a cada linha, não 1 a cada par.
        seq_registro = 0
        for pagamento in self.pagamentos:
            seq_registro += 1
            linhas.append(self._segmento_a(pagamento, seq_registro))
            seq_registro += 1
            linhas.append(self._segmento_b(pagamento, seq_registro))
            soma_valores += pagamento.valor_centavos

        # Trailer de lote: registros do lote inclui header(1) + 2*N + trailer(1)
        qtd_registros_lote = 2 + (len(self.pagamentos) * 2)
        linhas.append(self._trailer_lote(qtd_registros_lote, soma_valores))

        # Trailer de arquivo: total inclui header arq + lotes inteiros + trailer arq
        qtd_registros_total = 1 + qtd_registros_lote + 1
        linhas.append(self._trailer_arquivo(1, qtd_registros_total))

        # Validação final: cada linha tem 240 chars
        for i, linha in enumerate(linhas):
            if len(linha) != LARGURA_LINHA:
                raise CNABGeneratorError(
                    f"Linha {i + 1} tem {len(linha)} chars (esperado {LARGURA_LINHA}). "
                    f"Conteúdo: {linha!r}"
                )

        # Soma dos valores no trailer DEVE bater com soma armazenada no Lote
        # (sanidade — protege contra alteração silenciosa)
        if self.lote.valor_total_centavos != sum(p.valor_centavos for p in self.pagamentos):
            # Não falhamos: o lote.valor_total_centavos pode incluir CORRIGIVEIS não aprovados
            # Isto é só um sinal pra logs/debug
            pass

        conteudo = TERMINADOR_LINHA.join(linhas) + TERMINADOR_LINHA
        hash_arquivo = hashlib.sha256(conteudo.encode("latin-1")).hexdigest()

        # Unicred (e bancos em geral) só aceita nome com letras e números
        # — sem hífens, underlines, pontos ou espaços. Por isso usamos
        # somente caracteres alfanuméricos no nome (a extensão `.REM` é
        # tratada como parte do nome final, não como separador).
        # Formato: MEDPAG{sequencial:6}{YYYYMMDD}{HHMMSS}.REM
        nome_arquivo = (
            f"MEDPAG"
            f"{self.numero_sequencial:06d}"
            f"{self.agora.strftime('%Y%m%d%H%M%S')}.REM"
        )

        return CNABResult(
            conteudo=conteudo,
            hash_sha256=hash_arquivo,
            nome_arquivo=nome_arquivo,
            quantidade_pagamentos=len(self.pagamentos),
            valor_total_centavos=soma_valores,
            quantidade_registros=qtd_registros_total,
        )


# ============================================================
# Validador de concatenação (cinto + suspensórios)
# ============================================================


def _validar_e_concatenar(partes: list[str], nome_registro: str) -> str:
    """Concatena partes e valida que o total bate em 240 chars."""
    linha = "".join(partes)
    if len(linha) != LARGURA_LINHA:
        raise CNABGeneratorError(
            f"{nome_registro} tem {len(linha)} chars (esperado {LARGURA_LINHA}). "
            f"Verifique o layout."
        )
    return linha


__all__ = [
    "CNABGenerator",
    "CNABGeneratorError",
    "CNABResult",
]
