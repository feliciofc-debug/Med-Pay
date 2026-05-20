"""Testes do service de importação de planilha."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from app.core.exceptions import (
    LoteFormatoNaoReconhecidoError,
    LoteVazioError,
)
from app.services.importacao import (
    calcular_hash_conteudo,
    importar_planilha,
)


def _make_xlsx(df: pd.DataFrame) -> bytes:
    """Helper: serializa DataFrame em bytes XLSX."""
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def _make_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


class TestCalcularHash:
    def test_hash_e_deterministico(self) -> None:
        b = b"conteudo qualquer"
        assert calcular_hash_conteudo(b) == calcular_hash_conteudo(b)

    def test_hashs_diferentes_pra_conteudos_diferentes(self) -> None:
        assert calcular_hash_conteudo(b"a") != calcular_hash_conteudo(b"b")

    def test_hash_tem_64_chars(self) -> None:
        assert len(calcular_hash_conteudo(b"x")) == 64


class TestImportarPlanilhaBasico:
    """Casos felizes."""

    def test_xlsx_simples(self) -> None:
        df = pd.DataFrame(
            {
                "CPF": ["111.444.777-35", "222.333.444-55"],
                "Nome": ["José Silva", "Maria Souza"],
                "Banco": ["136", "001"],
                "Agência": ["1234", "5678"],
                "Conta": ["12345-6", "98765-4"],
                "Valor": ["1500,00", "2000,50"],
            }
        )
        resultado = importar_planilha(_make_xlsx(df), "lote.xlsx")
        assert resultado.total_linhas == 2
        assert len(resultado.linhas) == 2
        l0 = resultado.linhas[0]
        assert l0.numero_linha == 2  # primeira linha de dado depois do header
        assert l0.cpf_raw == "111.444.777-35"
        assert l0.nome_raw == "José Silva"
        assert l0.banco_raw == "136"
        assert l0.valor_raw == "1500,00"

    def test_csv_simples(self) -> None:
        df = pd.DataFrame(
            {
                "CPF": ["111.444.777-35"],
                "Nome": ["José"],
                "Valor": ["100,00"],
            }
        )
        resultado = importar_planilha(_make_csv(df), "lote.csv")
        assert resultado.total_linhas == 1
        assert resultado.linhas[0].nome_raw == "José"

    def test_mapeamento_aliases(self) -> None:
        """Aceita 'Documento' como CPF, 'Beneficiário' como nome, etc."""
        df = pd.DataFrame(
            {
                "Documento": ["111.444.777-35"],
                "Beneficiário": ["Dr. Silva"],
                "Valor Bruto": ["500"],
            }
        )
        resultado = importar_planilha(_make_xlsx(df), "x.xlsx")
        assert resultado.mapeamento_usado["cpf"] == "Documento"
        assert resultado.mapeamento_usado["nome"] == "Beneficiário"
        assert resultado.mapeamento_usado["valor"] == "Valor Bruto"

    def test_mapeamento_override_do_cliente(self) -> None:
        """Cliente pode salvar mapeamento custom."""
        df = pd.DataFrame(
            {
                "FOO": ["111.444.777-35"],
                "BAR": ["José"],
                "BAZ": ["100"],
            }
        )
        override = {"cpf": "FOO", "nome": "BAR", "valor": "BAZ"}
        resultado = importar_planilha(
            _make_xlsx(df), "x.xlsx", mapeamento_cliente=override
        )
        assert resultado.linhas[0].cpf_raw == "111.444.777-35"
        assert resultado.linhas[0].nome_raw == "José"


class TestErros:
    def test_arquivo_vazio_levanta(self) -> None:
        with pytest.raises(LoteVazioError):
            importar_planilha(b"", "x.xlsx")

    def test_planilha_sem_linhas(self) -> None:
        df = pd.DataFrame({"CPF": [], "Nome": [], "Valor": []})
        with pytest.raises(LoteVazioError):
            importar_planilha(_make_xlsx(df), "x.xlsx")

    def test_colunas_obrigatorias_faltando(self) -> None:
        # Falta a coluna 'valor' (nem alias)
        df = pd.DataFrame(
            {
                "CPF": ["111.444.777-35"],
                "Nome": ["José"],
            }
        )
        with pytest.raises(LoteFormatoNaoReconhecidoError) as exc_info:
            importar_planilha(_make_xlsx(df), "x.xlsx")
        assert "valor" in str(exc_info.value).lower()


class TestPreservacaoZerosEsquerda:
    def test_xlsx_preserva_zeros_a_esquerda_do_cpf(self) -> None:
        """Excel cospe zeros à esquerda — nosso reader força string e preserva."""
        df = pd.DataFrame(
            {
                "CPF": ["04223830000"],  # CPF começando com 0
                "Nome": ["Pessoa"],
                "Valor": ["100"],
            }
        )
        resultado = importar_planilha(_make_xlsx(df), "x.xlsx")
        assert resultado.linhas[0].cpf_raw == "04223830000"
