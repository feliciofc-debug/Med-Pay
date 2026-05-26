"""Classe-base FEBRABAN 240 — comum a todos os bancos do MedPag.

A grande maioria do layout CNAB 240 é PADRÃO FEBRABAN: mesmas posições,
mesma sequência de registros (Header Arquivo → Header Lote → N×(Seg A + Seg B)
→ Trailer Lote → Trailer Arquivo), mesmas regras de validação.

O que muda banco a banco:
    - Código do banco (3 dígitos)
    - Versão do layout de arquivo / lote (3 dígitos cada)
    - Nome do banco (30 chars no header)
    - Formato do campo "código de convênio" (20 chars, mas cada banco
      preenche de um jeito)
    - Códigos de câmara (compensação) específicos
    - Algumas posições reservadas livres têm uso específico (Bradesco
      usa pra ID da empresa líder, Itaú usa pra tipo serviço de folha…)

Esta classe-base implementa todo o esqueleto e expõe hooks (métodos
sobrescrevíveis) para que cada subclasse plugue suas particularidades.

REGRAS INEGOCIÁVEIS (válidas pra qualquer banco):
- Cada linha = EXATAMENTE 240 caracteres
- Hash SHA-256 do arquivo é registrado em Auditoria
- Trailer bate qtd × soma_valor com os detalhes
- Conta pagadora vem criptografada e é decifrada AQUI (dado sensível)
- Só pagamentos com status APROVADO entram
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
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
TIPO_SERVICO_FOLHA = "30"  # folha de pagamento (FEBRABAN)
FORMA_LANCAMENTO_CC = "01"  # crédito conta corrente
DENSIDADE = "01600"


@dataclass(slots=True)
class CNABResult:
    """Resultado da geração do arquivo CNAB."""

    conteudo: str
    hash_sha256: str
    nome_arquivo: str
    quantidade_pagamentos: int
    valor_total_centavos: int
    quantidade_registros: int
    banco_codigo: str = ""  # informativo: quem gerou esse arquivo

    @property
    def conteudo_bytes(self) -> bytes:
        """Bytes em latin-1 (encoding tradicional do CNAB)."""
        return self.conteudo.encode("latin-1")

    @property
    def tamanho_bytes(self) -> int:
        return len(self.conteudo_bytes)


class CNABGeneratorError(Exception):
    """Erro na geração do CNAB (regra de negócio quebrada)."""


def _validar_e_concatenar(partes: list[str], nome_registro: str) -> str:
    """Concatena partes e valida que o total bate em 240 chars."""
    linha = "".join(partes)
    if len(linha) != LARGURA_LINHA:
        raise CNABGeneratorError(
            f"{nome_registro} tem {len(linha)} chars (esperado {LARGURA_LINHA}). "
            f"Verifique o layout."
        )
    return linha


# ============================================================
# Base abstrata
# ============================================================


class CNABGeneratorBase(ABC):
    """Esqueleto FEBRABAN 240 — subclasses preenchem o que é por banco."""

    # ------- Constantes que cada subclasse SOBRESCREVE -------
    CODIGO_BANCO: str = ""        # ex.: "136" (Unicred), "341" (Itaú), "237" (Bradesco)
    NOME_BANCO: str = ""          # ex.: "UNICRED" (30 chars)
    VERSAO_LAYOUT_ARQUIVO: str = "103"
    VERSAO_LAYOUT_LOTE: str = "046"
    # Prefixo do nome do arquivo gerado. Cada banco tem convenção:
    # Unicred não exige nada, Bradesco prefere CB+sequencial, Itaú aceita livre.
    PREFIXO_NOME_ARQUIVO: str = "MEDPAG"
    # Extensão padrão (Unicred/Itaú usam .REM, Bradesco aceita .TXT/.REM)
    EXTENSAO_NOME_ARQUIVO: str = "REM"

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

        if not self.CODIGO_BANCO:
            raise CNABGeneratorError(
                f"{type(self).__name__} não declarou CODIGO_BANCO. "
                "Esta classe deve ser subclasse de CNABGeneratorBase."
            )

    # ============================================================
    # Helpers comuns
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

    def _conta_pagadora(self) -> tuple[str, str, str, str]:
        """Retorna (agencia_5, agencia_dv_1, conta_12, conta_dv_1)."""
        agencia = (self.empresa.agencia or "").rjust(5, "0")
        agencia_dv = self.empresa.agencia_dv or "0"
        conta_plain = decrypt(self.empresa.conta_encrypted)
        conta = "".join(c for c in conta_plain if c.isdigit()).zfill(12)
        conta_dv = self.empresa.conta_dv or "0"
        return agencia, agencia_dv, conta, conta_dv

    def _camara_para(self, banco_codigo_destino: str | None) -> str:
        """Câmara/forma de compensação no Segmento A.

        FEBRABAN padrão:
            000 = mesmo banco (TED/crédito interno)
            018 = TED entre bancos
            700 = DOC
        Bancos podem usar outros (Bradesco às vezes 700 pra DOC abaixo de 5k).
        """
        if not banco_codigo_destino:
            return "000"
        if banco_codigo_destino == self.CODIGO_BANCO:
            return "000"
        return "018"

    def _nome_arquivo(self) -> str:
        """Nome do arquivo de remessa.

        Formato base: {PREFIXO}{seq:6}{YYYYMMDDHHMMSS}.{ext}
        — só caracteres alfanuméricos + ponto antes da extensão.
        """
        return (
            f"{self.PREFIXO_NOME_ARQUIVO}"
            f"{self.numero_sequencial:06d}"
            f"{self.agora.strftime('%Y%m%d%H%M%S')}."
            f"{self.EXTENSAO_NOME_ARQUIVO}"
        )

    # ============================================================
    # Convênio — hook que cada banco implementa
    # ============================================================

    def _codigo_convenio_20(self) -> str:
        """Bloco de 20 chars na posição 33-52 dos headers.

        FEBRABAN deixa esse campo livre — cada banco usa de um jeito.
        Default: pega o codigo_convenio da empresa e completa com brancos
        até 20 chars (caso Unicred).

        Subclasses devem sobrescrever quando o banco exigir formato
        específico (Itaú: tipo serviço + agência + conta + DV).
        """
        return fmt_alfa(self.empresa.codigo_convenio or "", 20)

    # ============================================================
    # Registros — implementação padrão FEBRABAN com hooks
    # ============================================================

    def _header_arquivo(self) -> str:
        agencia, agencia_dv, conta, conta_dv = self._conta_pagadora()

        partes: list[str] = [
            self.CODIGO_BANCO,                                   # 001-003
            "0000",                                              # 004-007 (header arq)
            "0",                                                 # 008
            fmt_brancos(9),                                      # 009-017 reservado
            self._tipo_inscricao_codigo,                         # 018
            fmt_num(self.empresa.cnpj_cpf, 14),                  # 019-032
            self._codigo_convenio_20(),                          # 033-052 (20 chars)
            fmt_num(agencia, 5),                                 # 053-057
            fmt_alfa(agencia_dv, 1),                             # 058
            fmt_num(conta, 12),                                  # 059-070
            fmt_alfa(conta_dv, 1),                               # 071
            fmt_alfa(conta_dv, 1),                               # 072 (DV combinado)
            fmt_alfa(self.empresa.razao_social, 30),             # 073-102
            fmt_alfa(self.NOME_BANCO, 30),                       # 103-132
            fmt_brancos(10),                                     # 133-142 filler
            "1",                                                 # 143 (1=remessa)
            self._data_geracao,                                  # 144-151
            self._hora_geracao,                                  # 152-157
            fmt_num(self.numero_sequencial, 6),                  # 158-163
            self.VERSAO_LAYOUT_ARQUIVO,                          # 164-166
            DENSIDADE,                                           # 167-171
            fmt_brancos(20),                                     # 172-191 reservado banco
            fmt_brancos(20),                                     # 192-211 reservado empresa
            fmt_brancos(29),                                     # 212-240 filler
        ]
        return _validar_e_concatenar(partes, "Header de Arquivo")

    def _header_lote(self) -> str:
        agencia, agencia_dv, conta, conta_dv = self._conta_pagadora()
        # Conta + agência + DV juntos em 20 chars
        conta_agencia_dv = (
            fmt_num(agencia, 5)
            + fmt_alfa(agencia_dv, 1)
            + fmt_num(conta, 12)
            + fmt_alfa(conta_dv, 1)
            + fmt_alfa(conta_dv, 1)
        )

        partes: list[str] = [
            self.CODIGO_BANCO,                                   # 001-003
            fmt_num(self.codigo_lote, 4),                        # 004-007
            "1",                                                 # 008
            "C",                                                 # 009 (C=Crédito)
            TIPO_SERVICO_FOLHA,                                  # 010-011
            FORMA_LANCAMENTO_CC,                                 # 012-013
            self.VERSAO_LAYOUT_LOTE,                             # 014-016
            " ",                                                 # 017 filler
            self._tipo_inscricao_codigo,                         # 018
            fmt_num(self.empresa.cnpj_cpf, 14),                  # 019-032
            self._codigo_convenio_20(),                          # 033-052
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

    def _segmento_a(self, pagamento: Pagamento, sequencial: int) -> str:
        agencia = (
            decrypt(pagamento.agencia_encrypted)
            if pagamento.agencia_encrypted else ""
        )
        conta = (
            decrypt(pagamento.conta_encrypted)
            if pagamento.conta_encrypted else ""
        )

        agencia_num = "".join(c for c in agencia if c.isdigit()).zfill(5)
        conta_digitos = "".join(c for c in conta if c.isdigit()).zfill(12)
        camara = self._camara_para(pagamento.banco_codigo)

        partes: list[str] = [
            self.CODIGO_BANCO,                                   # 001-003
            fmt_num(self.codigo_lote, 4),                        # 004-007
            "3",                                                 # 008
            fmt_num(sequencial, 5),                              # 009-013
            "A",                                                 # 014
            "0",                                                 # 015 (movimento=inclusão)
            "00",                                                # 016-017
            camara,                                              # 018-020
            fmt_num(pagamento.banco_codigo or "0", 3),           # 021-023
            agencia_num,                                         # 024-028
            "0",                                                 # 029 (DV agência)
            conta_digitos,                                       # 030-041
            "0",                                                 # 042 (DV conta)
            "0",                                                 # 043 (DV ag+conta)
            fmt_alfa(pagamento.nome, 30),                        # 044-073
            fmt_alfa(str(pagamento.id)[:20], 20),                # 074-093 ID
            self._data_geracao,                                  # 094-101 data efetiva
            "BRL",                                               # 102-104
            fmt_zeros(15),                                       # 105-119
            fmt_num(pagamento.valor_centavos, 15),               # 120-134
            fmt_brancos(15),                                     # 135-149
            fmt_brancos(8),                                      # 150-157
            fmt_brancos(15),                                     # 158-172
            fmt_alfa(self.lote.referencia or "", 40),            # 173-212
            "10",                                                # 213-214 finalidade DOC
            fmt_brancos(5),                                      # 215-219
            "0",                                                 # 220 (aviso favorecido)
            fmt_brancos(4),                                      # 221-224
            fmt_brancos(6),                                      # 225-230
            fmt_brancos(10),                                     # 231-240
        ]
        return _validar_e_concatenar(partes, f"Segmento A (seq {sequencial})")

    def _segmento_b(self, pagamento: Pagamento, sequencial: int) -> str:
        cpf = decrypt(pagamento.cpf_encrypted) if pagamento.cpf_encrypted else ""
        cpf_digitos = "".join(c for c in cpf if c.isdigit())
        tipo_inscricao = "1" if len(cpf_digitos) == 11 else "2"

        partes: list[str] = [
            self.CODIGO_BANCO,                                   # 001-003
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

    def _trailer_lote(self, qtd_registros_lote: int, soma_valores: int) -> str:
        partes: list[str] = [
            self.CODIGO_BANCO,                                   # 001-003
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

    def _trailer_arquivo(self, qtd_lotes: int, qtd_registros_total: int) -> str:
        partes: list[str] = [
            self.CODIGO_BANCO,                                   # 001-003
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
    # Geração principal
    # ============================================================

    def gerar(self) -> CNABResult:
        """Monta o arquivo, valida largura por linha e calcula hash."""
        if not self.pagamentos:
            raise CNABGeneratorError(
                "Lote não tem nenhum pagamento APROVADO — nada a gerar"
            )

        linhas: list[str] = [self._header_arquivo(), self._header_lote()]

        soma_valores = 0
        # Sequencial dentro do lote: avança 1 a cada linha (Seg A + Seg B = 2)
        seq_registro = 0
        for pagamento in self.pagamentos:
            seq_registro += 1
            linhas.append(self._segmento_a(pagamento, seq_registro))
            seq_registro += 1
            linhas.append(self._segmento_b(pagamento, seq_registro))
            soma_valores += pagamento.valor_centavos

        qtd_registros_lote = 2 + (len(self.pagamentos) * 2)
        linhas.append(self._trailer_lote(qtd_registros_lote, soma_valores))

        qtd_registros_total = 1 + qtd_registros_lote + 1
        linhas.append(self._trailer_arquivo(1, qtd_registros_total))

        # Validação final defensiva
        for i, linha in enumerate(linhas):
            if len(linha) != LARGURA_LINHA:
                raise CNABGeneratorError(
                    f"Linha {i + 1} tem {len(linha)} chars "
                    f"(esperado {LARGURA_LINHA}). Conteúdo: {linha!r}"
                )

        conteudo = TERMINADOR_LINHA.join(linhas) + TERMINADOR_LINHA
        hash_arquivo = hashlib.sha256(conteudo.encode("latin-1")).hexdigest()

        return CNABResult(
            conteudo=conteudo,
            hash_sha256=hash_arquivo,
            nome_arquivo=self._nome_arquivo(),
            quantidade_pagamentos=len(self.pagamentos),
            valor_total_centavos=soma_valores,
            quantidade_registros=qtd_registros_total,
            banco_codigo=self.CODIGO_BANCO,
        )


__all__ = [
    "CNABGeneratorBase",
    "CNABGeneratorError",
    "CNABResult",
    "LARGURA_LINHA",
    "TERMINADOR_LINHA",
    "DENSIDADE",
    "TIPO_SERVICO_FOLHA",
    "FORMA_LANCAMENTO_CC",
]
