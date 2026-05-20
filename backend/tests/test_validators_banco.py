"""Testes do validador de dados bancários."""

from __future__ import annotations

import pytest

from app.validators.banco import (
    StatusBanco,
    listar_bancos_suportados,
    normalizar_codigo_banco,
    obter_banco,
    validar_dados_bancarios,
)


class TestNormalizacao:
    def test_adiciona_zero_a_esquerda(self) -> None:
        assert normalizar_codigo_banco("1") == "001"
        assert normalizar_codigo_banco("33") == "033"
        assert normalizar_codigo_banco("136") == "136"

    def test_aceita_inteiro(self) -> None:
        assert normalizar_codigo_banco(1) == "001"
        assert normalizar_codigo_banco(136) == "136"

    def test_remove_caracteres_nao_numericos(self) -> None:
        assert normalizar_codigo_banco("BB-001") == "001"

    def test_vazio_retorna_vazio(self) -> None:
        assert normalizar_codigo_banco("") == ""
        assert normalizar_codigo_banco(None) == ""


class TestObterBanco:
    def test_unicred_existe(self) -> None:
        regra = obter_banco("136")
        assert regra is not None
        assert regra.nome == "Unicred"
        assert regra.suportado is True

    def test_codigo_inexistente_retorna_none(self) -> None:
        assert obter_banco("999") is None

    def test_normaliza_antes_de_buscar(self) -> None:
        # "1" deveria virar "001" e achar BB
        regra = obter_banco("1")
        assert regra is not None
        assert regra.nome == "Banco do Brasil"


class TestListagem:
    def test_unicred_esta_na_lista_de_suportados(self) -> None:
        suportados = listar_bancos_suportados()
        nomes = [b.nome for b in suportados]
        assert "Unicred" in nomes

    def test_apenas_unicred_no_mvp(self) -> None:
        """No MVP, só Unicred deve estar marcado como suportado."""
        suportados = listar_bancos_suportados()
        assert len(suportados) == 1
        assert suportados[0].codigo == "136"


class TestValidacaoUnicred:
    """Caminho feliz com o banco do MVP."""

    def test_dados_validos(self) -> None:
        resultado = validar_dados_bancarios("136", "1234", "12345")
        assert resultado.is_valido
        assert resultado.banco_codigo == "136"
        assert resultado.banco_nome == "Unicred"

    def test_aceita_banco_como_int(self) -> None:
        resultado = validar_dados_bancarios(136, "1234", "12345")
        assert resultado.is_valido

    def test_agencia_com_formatacao(self) -> None:
        resultado = validar_dados_bancarios("136", "1234-5", "12345")
        # 1234-5 vira "12345" depois de limpar — extrapolaria o tamanho
        # Unicred aceita agência de 4 dígitos, então isso deve falhar
        assert resultado.codigo_erro == "AGENCIA_INVALIDA"

    def test_conta_com_digito_verificador(self) -> None:
        # Conta com DV separado por traço
        resultado = validar_dados_bancarios("136", "1234", "12345-6")
        # Deve limpar e ficar "123456" - 6 dígitos
        assert resultado.is_valido
        assert resultado.conta_limpa == "123456"


class TestValidacaoFalhas:
    def test_banco_vazio(self) -> None:
        resultado = validar_dados_bancarios("", "1234", "12345")
        assert resultado.status == StatusBanco.INVALIDO
        assert resultado.codigo_erro == "BANCO_INVALIDO"

    def test_banco_nao_existe(self) -> None:
        resultado = validar_dados_bancarios("999", "1234", "12345")
        assert resultado.codigo_erro == "BANCO_INVALIDO"

    def test_banco_nao_suportado(self) -> None:
        """Itaú existe mas não está habilitado no MVP."""
        resultado = validar_dados_bancarios("341", "1234", "12345")
        assert resultado.status == StatusBanco.NAO_SUPORTADO
        assert resultado.codigo_erro == "BANCO_NAO_SUPORTADO"
        assert "Itaú" in resultado.mensagem

    def test_agencia_vazia(self) -> None:
        resultado = validar_dados_bancarios("136", "", "12345")
        assert resultado.codigo_erro == "AGENCIA_INVALIDA"
        assert "não informada" in resultado.mensagem

    def test_agencia_muito_curta(self) -> None:
        resultado = validar_dados_bancarios("136", "12", "12345")
        assert resultado.codigo_erro == "AGENCIA_INVALIDA"

    def test_conta_vazia(self) -> None:
        resultado = validar_dados_bancarios("136", "1234", "")
        assert resultado.codigo_erro == "CONTA_INVALIDA"

    def test_conta_muito_curta(self) -> None:
        resultado = validar_dados_bancarios("136", "1234", "123")
        assert resultado.codigo_erro == "CONTA_INVALIDA"


@pytest.mark.parametrize(
    "banco,agencia,conta,deve_validar",
    [
        ("136", "1234", "12345", True),
        ("136", "1234", "1234567890", True),  # conta no limite máximo
        ("136", "1234", "12345678901", False),  # excede tamanho
        ("136", "12", "12345", False),  # agência curta
        ("999", "1234", "12345", False),  # banco inexistente
    ],
)
def test_casos_parametrizados(
    banco: str, agencia: str, conta: str, deve_validar: bool
) -> None:
    resultado = validar_dados_bancarios(banco, agencia, conta)
    assert resultado.is_valido == deve_validar
