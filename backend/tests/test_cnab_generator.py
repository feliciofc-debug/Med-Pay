"""Testes do gerador de CNAB 240 Unicred.

Estes testes não usam banco de dados — montam objetos models in-memory
e validam o conteúdo gerado.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from app.core.crypto import encrypt
from app.models.empresa_config import EmpresaConfig, TipoInscricao
from app.models.lote import Lote, StatusLote
from app.models.pagamento import Pagamento, StatusPagamento
from app.services.cnab_generator import (
    CNABGenerator,
    CNABGeneratorError,
)

LARGURA_LINHA = 240


def _make_empresa() -> EmpresaConfig:
    """Empresa de teste (Unicred fake)."""
    e = EmpresaConfig()
    e.id = uuid4()
    e.razao_social = "MEDPAG SERVICOS LTDA"
    e.nome_fantasia = None
    e.tipo_inscricao = TipoInscricao.CNPJ
    e.cnpj_cpf = "12345678000199"
    e.banco_codigo = "136"
    e.agencia = "1234"
    e.agencia_dv = "0"
    e.conta_encrypted = encrypt("123456789012")
    e.conta_dv = "0"
    e.conta_mascarada = "****9012"
    e.codigo_convenio = "0000123"
    e.endereco_logradouro = "RUA DAS FLORES"
    e.endereco_numero = "100"
    e.endereco_complemento = None
    e.endereco_cidade = "PORTO ALEGRE"
    e.endereco_cep = "90000000"
    e.endereco_uf = "RS"
    e.proximo_numero_sequencial = 1
    e.ativo = True
    return e


def _make_lote() -> Lote:
    lote = Lote()
    lote.id = uuid4()
    lote.cliente_id = uuid4()
    lote.nome_arquivo = "lote_teste.xlsx"
    lote.hash_conteudo = "0" * 64
    lote.referencia = "FOLHA JUNHO 2026"
    lote.status = StatusLote.APROVADO
    lote.total_pagamentos = 0
    lote.total_validos = 0
    lote.total_corrigiveis = 0
    lote.total_bloqueados = 0
    lote.valor_total_centavos = 0
    return lote


def _make_pagamento(
    nome: str = "JOSE DA SILVA",
    valor_centavos: int = 150000,
    cpf: str = "11144477735",
    banco: str = "136",
) -> Pagamento:
    p = Pagamento()
    p.id = uuid4()
    p.lote_id = uuid4()
    p.linha_planilha = 2
    p.cpf_encrypted = encrypt(cpf)
    p.cpf_hash = "x" * 64
    p.cpf_mascarado = "XXX.XXX.XXX-35"
    p.cpf_original = cpf
    p.nome = nome
    p.banco_codigo = banco
    p.agencia_encrypted = encrypt("9876")
    p.conta_encrypted = encrypt("1234567")
    p.conta_mascarada = "****4567"
    p.valor_centavos = valor_centavos
    p.status = StatusPagamento.APROVADO
    return p


# ============================================================
# Testes
# ============================================================


class TestCNABGerar:
    def test_gera_arquivo_valido(self) -> None:
        empresa = _make_empresa()
        lote = _make_lote()
        pagamentos = [
            _make_pagamento(nome="JOSE DA SILVA", valor_centavos=100000),
            _make_pagamento(nome="MARIA SOUZA", valor_centavos=200000),
        ]
        gen = CNABGenerator(
            lote=lote,
            pagamentos=pagamentos,
            empresa=empresa,
            numero_sequencial_arquivo=1,
            agora=datetime(2026, 5, 19, 14, 30, 25),
        )
        resultado = gen.gerar()

        # 1 header arq + 1 header lote + 2 (A+B) por pagamento + 1 trailer lote + 1 trailer arq
        # = 1 + 1 + 4 + 1 + 1 = 8 linhas
        linhas = resultado.conteudo.split("\r\n")
        # split inclui um vazio depois do último \r\n
        linhas = [linha for linha in linhas if linha]
        assert len(linhas) == 8

    def test_cada_linha_tem_240_chars(self) -> None:
        empresa = _make_empresa()
        lote = _make_lote()
        pagamentos = [_make_pagamento() for _ in range(5)]

        gen = CNABGenerator(
            lote=lote,
            pagamentos=pagamentos,
            empresa=empresa,
            numero_sequencial_arquivo=1,
        )
        resultado = gen.gerar()

        linhas = [linha for linha in resultado.conteudo.split("\r\n") if linha]
        for i, linha in enumerate(linhas):
            assert len(linha) == LARGURA_LINHA, (
                f"Linha {i} tem {len(linha)} chars: {linha!r}"
            )

    def test_terminador_crlf_no_final(self) -> None:
        empresa = _make_empresa()
        lote = _make_lote()
        pagamentos = [_make_pagamento()]

        gen = CNABGenerator(lote=lote, pagamentos=pagamentos, empresa=empresa,
                            numero_sequencial_arquivo=1)
        resultado = gen.gerar()

        assert resultado.conteudo.endswith("\r\n")

    def test_header_comeca_com_codigo_unicred(self) -> None:
        empresa = _make_empresa()
        lote = _make_lote()
        pagamentos = [_make_pagamento()]

        gen = CNABGenerator(lote=lote, pagamentos=pagamentos, empresa=empresa,
                            numero_sequencial_arquivo=42)
        resultado = gen.gerar()

        primeira = resultado.conteudo.split("\r\n")[0]
        assert primeira.startswith("136")  # banco Unicred
        assert primeira[3:7] == "0000"  # código de lote do header de arquivo
        assert primeira[7] == "0"  # tipo de registro

    def test_trailer_lote_tem_soma_correta(self) -> None:
        empresa = _make_empresa()
        lote = _make_lote()
        pagamentos = [
            _make_pagamento(valor_centavos=100000),
            _make_pagamento(valor_centavos=250000),
            _make_pagamento(valor_centavos=33333),
        ]
        soma_esperada = 100000 + 250000 + 33333

        gen = CNABGenerator(lote=lote, pagamentos=pagamentos, empresa=empresa,
                            numero_sequencial_arquivo=1)
        resultado = gen.gerar()

        assert resultado.valor_total_centavos == soma_esperada

        # Inspeciona o trailer do lote (penúltima linha)
        linhas = [linha for linha in resultado.conteudo.split("\r\n") if linha]
        trailer_lote = linhas[-2]
        assert trailer_lote[:3] == "136"
        assert trailer_lote[7] == "5"  # tipo registro

        # Posições 24-41 (1-indexed) = 23-41 (0-indexed) = 18 chars com soma
        soma_no_trailer = int(trailer_lote[23:41])
        assert soma_no_trailer == soma_esperada

    def test_trailer_lote_tem_quantidade_correta(self) -> None:
        empresa = _make_empresa()
        lote = _make_lote()
        pagamentos = [_make_pagamento() for _ in range(3)]
        # Header lote(1) + 3*2 detalhes(6) + trailer lote(1) = 8
        qtd_esperada = 8

        gen = CNABGenerator(lote=lote, pagamentos=pagamentos, empresa=empresa,
                            numero_sequencial_arquivo=1)
        resultado = gen.gerar()

        linhas = [linha for linha in resultado.conteudo.split("\r\n") if linha]
        trailer_lote = linhas[-2]
        # Posição 18-23 (1-indexed) = 17-23 (0-indexed) = 6 chars
        qtd_registros_lote = int(trailer_lote[17:23])
        assert qtd_registros_lote == qtd_esperada

    def test_trailer_arquivo_tem_total_correto(self) -> None:
        empresa = _make_empresa()
        lote = _make_lote()
        pagamentos = [_make_pagamento() for _ in range(2)]

        gen = CNABGenerator(lote=lote, pagamentos=pagamentos, empresa=empresa,
                            numero_sequencial_arquivo=1)
        resultado = gen.gerar()

        linhas = [linha for linha in resultado.conteudo.split("\r\n") if linha]
        trailer_arq = linhas[-1]
        assert trailer_arq[:3] == "136"
        assert trailer_arq[7] == "9"  # tipo registro

        # Posição 18-23 = qtd lotes (deve ser 1)
        qtd_lotes = int(trailer_arq[17:23])
        assert qtd_lotes == 1

        # Total: 1 header arq + (1 header lote + 4 detalhes + 1 trailer lote) + 1 trailer arq = 8
        qtd_total = int(trailer_arq[23:29])
        assert qtd_total == 8

    def test_filtra_pagamentos_nao_aprovados(self) -> None:
        empresa = _make_empresa()
        lote = _make_lote()
        p1 = _make_pagamento(valor_centavos=100000)
        p2 = _make_pagamento(valor_centavos=200000)
        p2.status = StatusPagamento.BLOQUEADO  # deve ser ignorado
        p3 = _make_pagamento(valor_centavos=300000)

        gen = CNABGenerator(
            lote=lote, pagamentos=[p1, p2, p3], empresa=empresa,
            numero_sequencial_arquivo=1,
        )
        resultado = gen.gerar()

        # Deve incluir só p1 e p3 (total 400000)
        assert resultado.quantidade_pagamentos == 2
        assert resultado.valor_total_centavos == 400000

    def test_lote_sem_aprovados_falha(self) -> None:
        empresa = _make_empresa()
        lote = _make_lote()
        p = _make_pagamento()
        p.status = StatusPagamento.BLOQUEADO

        gen = CNABGenerator(
            lote=lote, pagamentos=[p], empresa=empresa,
            numero_sequencial_arquivo=1,
        )
        with pytest.raises(CNABGeneratorError):
            gen.gerar()

    def test_hash_e_deterministico_para_mesmo_conteudo(self) -> None:
        empresa = _make_empresa()
        lote = _make_lote()
        pagamentos = [_make_pagamento(valor_centavos=100000)]
        agora = datetime(2026, 5, 19, 14, 30, 25)

        r1 = CNABGenerator(
            lote=lote, pagamentos=pagamentos, empresa=empresa,
            numero_sequencial_arquivo=1, agora=agora,
        ).gerar()
        r2 = CNABGenerator(
            lote=lote, pagamentos=pagamentos, empresa=empresa,
            numero_sequencial_arquivo=1, agora=agora,
        ).gerar()
        assert r1.hash_sha256 == r2.hash_sha256

    def test_sem_acentos_no_arquivo(self) -> None:
        empresa = _make_empresa()
        empresa.razao_social = "MÉDICOS ASSOCIADOS"
        lote = _make_lote()
        pagamentos = [_make_pagamento(nome="José da Conceição")]

        gen = CNABGenerator(lote=lote, pagamentos=pagamentos, empresa=empresa,
                            numero_sequencial_arquivo=1)
        resultado = gen.gerar()

        # Não pode haver caractere acentuado no arquivo final
        assert "É" not in resultado.conteudo
        assert "ã" not in resultado.conteudo
        assert "ç" not in resultado.conteudo
        assert "MEDICOS ASSOCIADOS" in resultado.conteudo
        assert "JOSE DA CONCEICAO" in resultado.conteudo

    def test_nome_arquivo_segue_padrao(self) -> None:
        empresa = _make_empresa()
        lote = _make_lote()
        pagamentos = [_make_pagamento()]

        gen = CNABGenerator(
            lote=lote, pagamentos=pagamentos, empresa=empresa,
            numero_sequencial_arquivo=1,
            agora=datetime(2026, 5, 19, 14, 30, 25),
        )
        resultado = gen.gerar()
        # Formato atual aceito pela Unicred: MEDPAG{seq:6}{YYYYMMDDHHMMSS}.REM
        # — só caracteres alfanuméricos e ponto, sem hífen/underscore.
        assert resultado.nome_arquivo.startswith("MEDPAG")
        assert resultado.nome_arquivo.endswith("20260519143025.REM")
        assert "000001" in resultado.nome_arquivo  # sequencial 1 zero-padded
