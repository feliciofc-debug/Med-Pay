"""Testes do validador local de chave PIX."""

from __future__ import annotations

import pytest

from app.validators.pix import (
    StatusPIX,
    TipoChavePIX,
    detectar_tipo,
    validar_chave_pix,
)


class TestAutoDeteccao:
    def test_email(self) -> None:
        assert detectar_tipo("maria@hospital.com.br") == TipoChavePIX.EMAIL

    def test_cpf(self) -> None:
        # CPF valido
        assert detectar_tipo("11144477735") == TipoChavePIX.CPF

    def test_cnpj(self) -> None:
        # CNPJ valido (11.222.333/0001-81)
        assert detectar_tipo("11222333000181") == TipoChavePIX.CNPJ

    def test_telefone_e164(self) -> None:
        assert detectar_tipo("+5521987654321") == TipoChavePIX.TELEFONE

    def test_telefone_sem_prefixo(self) -> None:
        # 11 digitos com 9 na 3a posicao -> celular
        assert detectar_tipo("21987654321") == TipoChavePIX.TELEFONE

    def test_evp(self) -> None:
        # UUID v4 estrito (3o grupo comeca com 4, 4o grupo com 8/9/a/b)
        assert (
            detectar_tipo("a1b2c3d4-1234-4234-9234-abcdef123456")
            == TipoChavePIX.ALEATORIA
        )

    def test_lixo_retorna_none(self) -> None:
        assert detectar_tipo("xyz123") is None
        assert detectar_tipo("") is None
        assert detectar_tipo(None) is None


class TestEmail:
    def test_email_valido(self) -> None:
        r = validar_chave_pix("felipe@gmail.com")
        assert r.is_valida
        assert r.tipo_detectado == TipoChavePIX.EMAIL
        assert r.chave_normalizada == "felipe@gmail.com"

    def test_email_uppercase_vira_lowercase(self) -> None:
        r = validar_chave_pix("Felipe@GMAIL.com")
        assert r.is_valida
        assert r.chave_normalizada == "felipe@gmail.com"

    def test_email_invalido(self) -> None:
        r = validar_chave_pix("nao-eh-email", tipo="EMAIL")
        assert not r.is_valida
        assert r.codigo_erro == "PIX_EMAIL_INVALIDO"


class TestCPF:
    def test_cpf_valido_sem_titular(self) -> None:
        r = validar_chave_pix("111.444.777-35")
        assert r.is_valida
        assert r.tipo_detectado == TipoChavePIX.CPF
        assert r.chave_normalizada == "11144477735"

    def test_cpf_invalido_dv(self) -> None:
        r = validar_chave_pix("11111111111", tipo="CPF")
        assert not r.is_valida
        assert r.codigo_erro == "PIX_CPF_INVALIDO"

    def test_cpf_bate_com_titular(self) -> None:
        r = validar_chave_pix(
            "111.444.777-35", cpf_titular="111.444.777-35"
        )
        assert r.is_valida

    def test_cpf_nao_bate_com_titular(self) -> None:
        # Chave PIX e' CPF de outra pessoa
        r = validar_chave_pix(
            "111.444.777-35", cpf_titular="98765432100"
        )
        assert not r.is_valida
        assert r.codigo_erro == "PIX_CPF_NAO_BATE"
        assert "OUTRA pessoa" in r.mensagem


class TestCNPJ:
    def test_cnpj_valido(self) -> None:
        r = validar_chave_pix("11.222.333/0001-81")
        assert r.is_valida
        assert r.tipo_detectado == TipoChavePIX.CNPJ
        assert r.chave_normalizada == "11222333000181"

    def test_cnpj_dv_errado(self) -> None:
        r = validar_chave_pix("11222333000199", tipo="CNPJ")
        assert not r.is_valida
        assert r.codigo_erro == "PIX_CNPJ_INVALIDO"


class TestTelefone:
    def test_telefone_com_mascara(self) -> None:
        r = validar_chave_pix("(21) 99999-8888", tipo="TELEFONE")
        assert r.is_valida
        assert r.chave_normalizada == "+5521999998888"

    def test_telefone_e164_completo(self) -> None:
        r = validar_chave_pix("+5521987654321", tipo="TELEFONE")
        assert r.is_valida
        assert r.chave_normalizada == "+5521987654321"

    def test_telefone_curto_invalido(self) -> None:
        r = validar_chave_pix("12345", tipo="TELEFONE")
        assert not r.is_valida


class TestEVP:
    def test_evp_valida(self) -> None:
        r = validar_chave_pix(
            "a1b2c3d4-1234-4234-9234-abcdef123456", tipo="ALEATORIA"
        )
        assert r.is_valida
        assert r.tipo_detectado == TipoChavePIX.ALEATORIA

    def test_evp_invalida(self) -> None:
        r = validar_chave_pix("nao-eh-uuid", tipo="ALEATORIA")
        assert not r.is_valida


class TestVazio:
    def test_chave_vazia(self) -> None:
        r = validar_chave_pix("")
        assert not r.is_valida
        assert r.codigo_erro == "PIX_VAZIO"

    def test_chave_none(self) -> None:
        r = validar_chave_pix(None)
        assert not r.is_valida


class TestTipoExplicitoErrado:
    def test_tipo_desconhecido(self) -> None:
        r = validar_chave_pix("qualquer", tipo="XPTO")
        assert not r.is_valida
        assert r.codigo_erro == "PIX_TIPO_INVALIDO"


@pytest.mark.parametrize(
    "chave,esperado",
    [
        ("felipe@medpag.com", True),
        ("(21) 99999-8888", True),
        ("11144477735", True),
        ("11222333000181", True),
        ("a1b2c3d4-1234-4234-9234-abcdef123456", True),
        ("", False),
        ("xyz", False),
    ],
)
def test_casos_validacao_auto(chave: str, esperado: bool) -> None:
    r = validar_chave_pix(chave)
    assert r.is_valida == esperado
