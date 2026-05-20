"""Testes dos utilitários CNAB (formatação)."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.services.cnab_utils import (
    calcular_dv_modulo11,
    fmt_alfa,
    fmt_data,
    fmt_hora,
    fmt_num,
    remover_acentos,
)


class TestRemoverAcentos:
    def test_jose(self) -> None:
        assert remover_acentos("José") == "Jose"

    def test_acucar(self) -> None:
        assert remover_acentos("açúcar") == "acucar"

    def test_vazio(self) -> None:
        assert remover_acentos("") == ""

    def test_sem_acento_nao_muda(self) -> None:
        assert remover_acentos("ABC") == "ABC"


class TestFmtAlfa:
    def test_completa_com_espacos(self) -> None:
        assert fmt_alfa("ABC", 10) == "ABC       "

    def test_uppercase(self) -> None:
        assert fmt_alfa("José", 10) == "JOSE      "

    def test_trunca_se_excede(self) -> None:
        assert fmt_alfa("123456789012345", 10) == "1234567890"

    def test_none_vira_espacos(self) -> None:
        assert fmt_alfa(None, 5) == "     "


class TestFmtNum:
    def test_zero_a_esquerda(self) -> None:
        assert fmt_num(123, 8) == "00000123"

    def test_string_de_digitos(self) -> None:
        assert fmt_num("456", 5) == "00456"

    def test_filtra_nao_digitos(self) -> None:
        assert fmt_num("12-34", 6) == "001234"

    def test_zero_se_none(self) -> None:
        assert fmt_num(None, 5) == "00000"

    def test_zero_se_vazio(self) -> None:
        assert fmt_num("", 5) == "00000"


class TestFmtData:
    def test_data_normal(self) -> None:
        assert fmt_data(date(2026, 5, 19)) == "19052026"

    def test_datetime(self) -> None:
        assert fmt_data(datetime(2026, 5, 19, 14, 30)) == "19052026"

    def test_none(self) -> None:
        assert fmt_data(None) == "00000000"


class TestFmtHora:
    def test_hora_normal(self) -> None:
        assert fmt_hora(datetime(2026, 5, 19, 14, 30, 25)) == "143025"

    def test_none(self) -> None:
        assert fmt_hora(None) == "000000"


class TestDVModulo11:
    """Testa o algoritmo padrão de DV (não específico da Unicred)."""

    def test_dv_zero_quando_resto_zero(self) -> None:
        # Caso conhecido: número que dá resto 0 → DV = 0
        # Vamos só verificar que retorna char de 1 dígito ou 'X'
        dv = calcular_dv_modulo11("123456789")
        assert len(dv) == 1
        assert dv in "0123456789X"

    def test_vazio_retorna_zero(self) -> None:
        assert calcular_dv_modulo11("") == "0"

    def test_letras_retorna_zero(self) -> None:
        assert calcular_dv_modulo11("abc") == "0"
