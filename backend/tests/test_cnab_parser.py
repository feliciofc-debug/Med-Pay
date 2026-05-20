"""Testes do parser de arquivo de retorno CNAB."""

from __future__ import annotations

import pytest

from app.core.exceptions import LoteFormatoNaoReconhecidoError
from app.services.cnab_parser import parsear_arquivo_retorno


def _segmento_a_retorno(
    *,
    sequencial: int = 1,
    nome: str = "JOSE DA SILVA",
    valor_centavos: int = 100000,
    id_documento: str = "abcd1234efgh5678",
    codigo_ocorrencia: str = "BD",
    codigo_lote: int = 1,
) -> str:
    """Constrói um Segmento A simulando o que o banco devolveria.

    240 chars exatos.
    """
    posicao = lambda inicio, fim, conteudo: conteudo.ljust(fim - inicio + 1)[
        : fim - inicio + 1
    ]

    nome_padded = nome.ljust(30)[:30]
    id_padded = id_documento.ljust(20)[:20]
    valor_str = str(valor_centavos).zfill(15)

    # Construímos posição por posição (1-indexed na doc, 0-indexed aqui)
    linha = (
        "136"                                # 001-003
        + str(codigo_lote).zfill(4)          # 004-007
        + "3"                                # 008
        + str(sequencial).zfill(5)           # 009-013
        + "A"                                # 014
        + "0"                                # 015
        + "00"                               # 016-017
        + "000"                              # 018-020 (camara)
        + "136"                              # 021-023 (banco favorecido)
        + "12345"                            # 024-028 (agência)
        + "0"                                # 029
        + "000000123456"                     # 030-041 (conta)
        + "0"                                # 042
        + "0"                                # 043
        + nome_padded                        # 044-073
        + id_padded                          # 074-093
        + "19052026"                         # 094-101
        + "BRL"                              # 102-104
        + "0" * 15                           # 105-119
        + valor_str                          # 120-134
        + " " * 15                           # 135-149
        + " " * 8                            # 150-157
        + " " * 15                           # 158-172
        + " " * 40                           # 173-212
        + "10"                               # 213-214
        + " " * 5                            # 215-219
        + "0"                                # 220
        + " " * 4                            # 221-224
        + " " * 6                            # 225-230
        + codigo_ocorrencia.ljust(10)[:10]   # 231-240 (códigos)
    )
    assert len(linha) == 240, f"Linha tem {len(linha)} chars"
    return linha


class TestParseArquivoRetorno:
    def test_parse_pagamento_pago(self) -> None:
        linha = _segmento_a_retorno(
            sequencial=1,
            nome="JOSE DA SILVA",
            valor_centavos=150000,
            id_documento="aaa-bbb-ccc",
            codigo_ocorrencia="BD",
        )
        # Adiciona header de arquivo + lote + trailer só pra parecer um arquivo real
        # mas o parser aceita só com Segmentos A
        conteudo = linha.encode("latin-1") + b"\r\n"

        resultado = parsear_arquivo_retorno(conteudo)
        assert len(resultado.pagamentos) == 1
        p = resultado.pagamentos[0]
        assert p.foi_pago is True
        assert p.valor_centavos == 150000
        assert p.codigo_ocorrencia == "BD"
        assert "Pago" in p.descricao_ocorrencia
        assert resultado.pagos == 1
        assert resultado.nao_pagos == 0

    def test_parse_pagamento_nao_pago(self) -> None:
        linha = _segmento_a_retorno(
            codigo_ocorrencia="AJ",  # Saldo insuficiente
        )
        conteudo = linha.encode("latin-1") + b"\r\n"

        resultado = parsear_arquivo_retorno(conteudo)
        p = resultado.pagamentos[0]
        assert p.foi_pago is False
        assert p.codigo_ocorrencia == "AJ"
        assert resultado.nao_pagos == 1

    def test_multiplos_pagamentos(self) -> None:
        linhas = [
            _segmento_a_retorno(sequencial=i, codigo_ocorrencia="BD" if i % 2 else "AJ")
            for i in range(1, 6)
        ]
        conteudo = "\r\n".join(linhas).encode("latin-1") + b"\r\n"

        resultado = parsear_arquivo_retorno(conteudo)
        assert len(resultado.pagamentos) == 5
        # Pares (i % 2 == 0) viram AJ (não pago), ímpares BD (pago)
        # Sequenciais 1,3,5 = BD; 2,4 = AJ
        assert resultado.pagos == 3
        assert resultado.nao_pagos == 2

    def test_arquivo_vazio_levanta(self) -> None:
        with pytest.raises(LoteFormatoNaoReconhecidoError):
            parsear_arquivo_retorno(b"")

    def test_arquivo_sem_segmentos_a(self) -> None:
        # Arquivo só com lixo
        conteudo = ("X" * 240 + "\r\n").encode("latin-1")
        with pytest.raises(LoteFormatoNaoReconhecidoError):
            parsear_arquivo_retorno(conteudo)

    def test_id_documento_e_extraido(self) -> None:
        linha = _segmento_a_retorno(id_documento="MEU-ID-CUSTOM-123")
        conteudo = linha.encode("latin-1")

        resultado = parsear_arquivo_retorno(conteudo)
        assert resultado.pagamentos[0].id_documento == "MEU-ID-CUSTOM-123"
