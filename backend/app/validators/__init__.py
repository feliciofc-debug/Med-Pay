"""Validadores puros (sem dependência de banco de dados).

Toda função aqui é determinística e pode ser testada isoladamente.
"""

from app.validators.banco import (
    ResultadoValidacaoBanco,
    StatusBanco,
    listar_bancos_suportados,
    validar_dados_bancarios,
)
from app.validators.cpf import (
    CPFStatus,
    ResultadoValidacaoCPF,
    formatar_cpf,
    limpar_cpf,
    validar_cpf,
)
from app.validators.valor import (
    ResultadoValidacaoValor,
    ValorStatus,
    parsear_valor_para_centavos,
    validar_valor,
)

__all__ = [
    "CPFStatus",
    "ResultadoValidacaoBanco",
    "ResultadoValidacaoCPF",
    "ResultadoValidacaoValor",
    "StatusBanco",
    "ValorStatus",
    "formatar_cpf",
    "limpar_cpf",
    "listar_bancos_suportados",
    "parsear_valor_para_centavos",
    "validar_cpf",
    "validar_dados_bancarios",
    "validar_valor",
]
