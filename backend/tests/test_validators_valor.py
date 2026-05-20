"""Testes do validador de valor monetário."""

from __future__ import annotations

import pytest

from app.validators.valor import (
    ValorStatus,
    parsear_valor_para_centavos,
    validar_valor,
)


class TestParsearValor:
    """parsear_valor_para_centavos aceita múltiplos formatos."""

    def test_formato_br_completo(self) -> None:
        assert parsear_valor_para_centavos("R$ 1.234,56") == 123456

    def test_formato_br_simples(self) -> None:
        assert parsear_valor_para_centavos("1234,56") == 123456

    def test_formato_us(self) -> None:
        assert parsear_valor_para_centavos("1234.56") == 123456

    def test_float_direto(self) -> None:
        assert parsear_valor_para_centavos(1234.56) == 123456

    def test_int_direto_assume_reais(self) -> None:
        # Inteiro é interpretado como reais (sem centavos)
        assert parsear_valor_para_centavos(1500) == 150000

    def test_zero(self) -> None:
        assert parsear_valor_para_centavos(0) == 0

    def test_vazio(self) -> None:
        assert parsear_valor_para_centavos("") is None
        assert parsear_valor_para_centavos(None) is None

    def test_lixo(self) -> None:
        assert parsear_valor_para_centavos("abc") is None

    def test_com_simbolo_real(self) -> None:
        assert parsear_valor_para_centavos("R$ 250,00") == 25000

    def test_centavos_e_milhar(self) -> None:
        assert parsear_valor_para_centavos("12.345,67") == 1234567


class TestValidarValor:
    def test_valor_normal(self) -> None:
        r = validar_valor("R$ 1.500,00")
        assert r.is_valido
        assert r.valor_centavos == 150000
        assert r.codigo_erro is None

    def test_valor_zero(self) -> None:
        r = validar_valor("0")
        assert r.status == ValorStatus.INVALIDO
        assert r.codigo_erro == "VALOR_ZERO"

    def test_valor_negativo(self) -> None:
        r = validar_valor("-100,00")
        # Negativo tb é VALOR_ZERO (genérico de "<=0")
        assert r.status == ValorStatus.INVALIDO
        assert r.codigo_erro == "VALOR_ZERO"

    def test_valor_lixo(self) -> None:
        r = validar_valor("não é número")
        assert r.codigo_erro == "VALOR_FORMATO_INVALIDO"

    def test_valor_vazio(self) -> None:
        r = validar_valor("")
        assert r.codigo_erro == "VALOR_FORMATO_INVALIDO"

    def test_valor_acima_do_max_e_suspeito(self) -> None:
        # Default max é R$ 100.000,00 (10_000_000 centavos)
        r = validar_valor("R$ 250.000,00")
        assert r.status == ValorStatus.SUSPEITO
        assert r.codigo_erro == "VALOR_SUSPEITO"
        assert "vírgula" in r.mensagem.lower()

    def test_valor_abaixo_do_min_e_suspeito(self) -> None:
        # Default min é R$ 1,00 (100 centavos)
        r = validar_valor("R$ 0,50")
        assert r.status == ValorStatus.SUSPEITO
        assert r.codigo_erro == "VALOR_SUSPEITO"

    def test_limites_customizados(self) -> None:
        r = validar_valor("R$ 50,00", valor_min_centavos=10000, valor_max_centavos=20000)
        assert r.status == ValorStatus.SUSPEITO  # < 10000


@pytest.mark.parametrize(
    "valor,centavos_esperado",
    [
        ("R$ 1.234,56", 123456),
        ("1.234,56", 123456),
        ("1234,56", 123456),
        ("1234.56", 123456),
        ("R$ 100,00", 10000),
        ("0,01", 1),
        (1234.56, 123456),
        (0.01, 1),
    ],
)
def test_parsing_parametrizado(
    valor: str | float, centavos_esperado: int
) -> None:
    assert parsear_valor_para_centavos(valor) == centavos_esperado
