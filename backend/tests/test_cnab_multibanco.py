"""Testes dos adapters multi-banco do CNAB (Unicred, Itaú, Bradesco).

Cada adapter precisa:
    - Gerar todas as linhas com EXATAMENTE 240 chars
    - Usar o código de banco correto nas posições 1-3 de cada registro
    - Manter o trailer batendo (qtd e soma) com os detalhes
    - Sair com nome de arquivo distinto (prefixo por banco)

Os testes não dependem do banco de dados (objetos in-memory).
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from app.core.crypto import encrypt
from app.models.empresa_config import BancoEmissor, EmpresaConfig, TipoInscricao
from app.models.lote import Lote, StatusLote
from app.models.pagamento import Pagamento, StatusPagamento
from app.services.cnab_base import LARGURA_LINHA
from app.services.cnab_bradesco import CNABGeneratorBradesco
from app.services.cnab_factory import criar_gerador_cnab
from app.services.cnab_itau import CNABGeneratorItau
from app.services.cnab_unicred import CNABGeneratorUnicred


def _empresa(banco: BancoEmissor) -> EmpresaConfig:
    e = EmpresaConfig()
    e.id = uuid4()
    e.razao_social = "MEDPAG SERVICOS LTDA"
    e.nome_fantasia = None
    e.tipo_inscricao = TipoInscricao.CNPJ
    e.cnpj_cpf = "12345678000199"
    e.banco_emissor = banco
    # banco_codigo legado: pode ficar Unicred, o adapter usa CODIGO_BANCO próprio
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
    e.proximo_numero_sequencial = 7
    e.ativo = True
    return e


def _lote() -> Lote:
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


def _pgto(nome: str, valor_centavos: int, banco_destino: str) -> Pagamento:
    p = Pagamento()
    p.id = uuid4()
    p.lote_id = uuid4()
    p.linha_planilha = 2
    p.cpf_encrypted = encrypt("11144477735")
    p.cpf_hash = "x" * 64
    p.cpf_mascarado = "XXX.XXX.XXX-35"
    p.cpf_original = "11144477735"
    p.nome = nome
    p.banco_codigo = banco_destino
    p.agencia_encrypted = encrypt("9876")
    p.conta_encrypted = encrypt("1234567")
    p.conta_mascarada = "****4567"
    p.valor_centavos = valor_centavos
    p.status = StatusPagamento.APROVADO
    return p


CASOS_BANCO = [
    pytest.param(BancoEmissor.UNICRED, "136", CNABGeneratorUnicred, id="unicred"),
    pytest.param(BancoEmissor.ITAU, "341", CNABGeneratorItau, id="itau"),
    pytest.param(
        BancoEmissor.BRADESCO, "237", CNABGeneratorBradesco, id="bradesco"
    ),
]


@pytest.mark.parametrize("banco_enum,codigo_banco,classe", CASOS_BANCO)
def test_factory_devolve_adapter_correto(
    banco_enum: BancoEmissor,
    codigo_banco: str,
    classe: type,
) -> None:
    empresa = _empresa(banco_enum)
    lote = _lote()
    pagamentos = [_pgto("JOSE", 100000, banco_destino=codigo_banco)]

    gen = criar_gerador_cnab(
        lote=lote,
        pagamentos=pagamentos,
        empresa=empresa,
        numero_sequencial_arquivo=1,
        agora=datetime(2026, 5, 26, 9, 0, 0),
    )
    assert isinstance(gen, classe)
    assert gen.CODIGO_BANCO == codigo_banco


@pytest.mark.parametrize("banco_enum,codigo_banco,_classe", CASOS_BANCO)
def test_largura_240_em_todas_as_linhas(
    banco_enum: BancoEmissor,
    codigo_banco: str,
    _classe: type,
) -> None:
    empresa = _empresa(banco_enum)
    lote = _lote()
    pagamentos = [
        _pgto("JOSE DA SILVA", 150000, banco_destino=codigo_banco),
        _pgto("MARIA SOUZA", 275050, banco_destino="001"),  # crédito p/ outro banco
    ]
    gen = criar_gerador_cnab(
        lote=lote,
        pagamentos=pagamentos,
        empresa=empresa,
        numero_sequencial_arquivo=42,
        agora=datetime(2026, 5, 26, 9, 0, 0),
    )
    resultado = gen.gerar()

    linhas = resultado.conteudo.split("\r\n")
    # última linha é vazia (terminator final)
    linhas = [l for l in linhas if l]
    # 1 header arq + 1 header lote + 2 pagamentos * 2 segmentos + 1 trailer lote + 1 trailer arq
    assert len(linhas) == 8, f"Esperado 8 linhas, veio {len(linhas)}"
    for i, linha in enumerate(linhas, start=1):
        assert len(linha) == LARGURA_LINHA, (
            f"[{banco_enum.value}] Linha {i} tem {len(linha)} chars "
            f"(esperado {LARGURA_LINHA})"
        )


@pytest.mark.parametrize("banco_enum,codigo_banco,_classe", CASOS_BANCO)
def test_codigo_do_banco_aparece_nas_3_primeiras_posicoes(
    banco_enum: BancoEmissor,
    codigo_banco: str,
    _classe: type,
) -> None:
    empresa = _empresa(banco_enum)
    lote = _lote()
    pagamentos = [_pgto("JOSE", 50000, banco_destino=codigo_banco)]

    gen = criar_gerador_cnab(
        lote=lote,
        pagamentos=pagamentos,
        empresa=empresa,
        numero_sequencial_arquivo=1,
        agora=datetime(2026, 5, 26, 9, 0, 0),
    )
    resultado = gen.gerar()

    for linha in resultado.conteudo.split("\r\n"):
        if not linha:
            continue
        assert linha[:3] == codigo_banco, (
            f"[{banco_enum.value}] linha começa com {linha[:3]!r}, "
            f"esperado {codigo_banco!r}"
        )

    assert resultado.banco_codigo == codigo_banco


@pytest.mark.parametrize("banco_enum,_codigo,_classe", CASOS_BANCO)
def test_trailer_bate_soma_e_quantidade(
    banco_enum: BancoEmissor,
    _codigo: str,
    _classe: type,
) -> None:
    empresa = _empresa(banco_enum)
    lote = _lote()
    pagamentos = [
        _pgto("A", 100000, banco_destino="001"),
        _pgto("B", 250000, banco_destino="033"),
        _pgto("C", 375000, banco_destino="237"),
    ]
    gen = criar_gerador_cnab(
        lote=lote,
        pagamentos=pagamentos,
        empresa=empresa,
        numero_sequencial_arquivo=1,
        agora=datetime(2026, 5, 26, 9, 0, 0),
    )
    resultado = gen.gerar()

    assert resultado.quantidade_pagamentos == 3
    assert resultado.valor_total_centavos == 100000 + 250000 + 375000
    # 1 header arq + 1 header lote + 2 * 3 detalhes + 1 trailer lote + 1 trailer arq
    assert resultado.quantidade_registros == 1 + 1 + 6 + 1 + 1


def test_nomes_de_arquivo_tem_prefixo_por_banco() -> None:
    """Cada banco gera arquivo com prefixo distinto pra triagem fácil."""
    lote = _lote()
    pgtos = [_pgto("JOSE", 50000, banco_destino="001")]
    agora = datetime(2026, 5, 26, 9, 0, 0)

    nomes: dict[str, str] = {}
    for banco in [BancoEmissor.UNICRED, BancoEmissor.ITAU, BancoEmissor.BRADESCO]:
        gen = criar_gerador_cnab(
            lote=lote,
            pagamentos=pgtos,
            empresa=_empresa(banco),
            numero_sequencial_arquivo=1,
            agora=agora,
        )
        nomes[banco.value] = gen.gerar().nome_arquivo

    # São distintos entre si (prefixo diferente)
    assert len({nomes["UNICRED"], nomes["ITAU"], nomes["BRADESCO"]}) == 3
    assert nomes["ITAU"].startswith("MEDPAGI")
    assert nomes["BRADESCO"].startswith("MEDPAGB")
    assert nomes["UNICRED"].startswith("MEDPAG") and not nomes["UNICRED"].startswith(
        "MEDPAGI"
    )
