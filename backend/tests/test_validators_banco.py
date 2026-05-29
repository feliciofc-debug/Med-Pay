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

    def test_principais_bancos_suportados(self) -> None:
        """Tabela de regras específicas cobre os principais bancos do mercado
        (Unicred, BB, Itaú, Bradesco, Santander, Caixa, Sicredi, Sicoob,
        Nubank, Inter, C6, Original, Safra, BTG).
        """
        suportados = listar_bancos_suportados()
        codigos = {b.codigo for b in suportados}
        # MVP exige Unicred (banco pagador)
        assert "136" in codigos
        # Cobertura de mercado mínima (cobre >85% dos prestadores BR)
        for codigo_minimo in {"001", "033", "104", "237", "260", "341", "748", "756"}:
            assert codigo_minimo in codigos, f"Banco {codigo_minimo} deveria estar suportado"


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
        # Unicred aceita agência de 4-5 dígitos; "1234-5" limpa pra "12345".
        # Hoje aceitamos esse range pra tolerar planilhas que trazem DV junto.
        assert resultado.is_valido
        assert resultado.agencia_limpa == "12345"

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

    def test_banco_inexistente(self) -> None:
        """Código que não consta na lista FEBRABAN é rejeitado."""
        resultado = validar_dados_bancarios("999", "1234", "12345")
        assert resultado.status == StatusBanco.INVALIDO
        assert resultado.codigo_erro == "BANCO_INVALIDO"
        assert "FEBRABAN" in resultado.mensagem

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
        ("136", "1234", "123456789012", True),  # conta no limite máximo (12)
        ("136", "1234", "1234567890123", False),  # excede tamanho (>12)
        ("136", "12", "12345", False),  # agência curta
        ("999", "1234", "12345", False),  # banco inexistente
    ],
)
def test_casos_parametrizados(
    banco: str, agencia: str, conta: str, deve_validar: bool
) -> None:
    resultado = validar_dados_bancarios(banco, agencia, conta)
    assert resultado.is_valido == deve_validar
