"""Parser de arquivo de retorno CNAB 240.

Lê o arquivo .ret que o banco devolve depois de processar a remessa.
Extrai os Segmentos A (com código de ocorrência) e usa o ID do
pagamento (que colocamos no campo "número do documento" durante a
geração) pra fechar o ciclo: marca cada Pagamento como PAGO ou NAO_PAGO.

REGRA: este parser é tolerante — formatos do banco podem ter pequenas
variações. Se uma linha for ignorada, segue processando as outras.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import LoteFormatoNaoReconhecidoError


# Tabela de códigos de ocorrência (alguns dos mais comuns FEBRABAN)
# Os códigos efetivamente devolvidos pela Unicred devem ser confirmados.
CODIGOS_OCORRENCIA: dict[str, str] = {
    "BD": "Pago",
    "00": "Pago",
    "AA": "Em aberto",
    "AC": "Pendente de débito",
    "AE": "Conta favorecido inválida",
    "AF": "Validação falhou",
    "AG": "Agência/conta favorecido encerrada",
    "AH": "CPF/CNPJ inválido",
    "AI": "Não autorizado pela cooperativa",
    "AJ": "Saldo insuficiente",
    "AK": "Conta inexistente",
    "AL": "Operação não permitida",
    "BC": "Estornado",
    "ZA": "Conta encerrada",
}

CODIGOS_DE_SUCESSO = {"BD", "00"}


@dataclass(slots=True)
class RetornoPagamento:
    """Resultado da leitura de um Segmento A no retorno."""

    sequencial: int
    nome_favorecido: str
    valor_centavos: int
    id_documento: str  # ID do pagamento que colocamos na geração
    codigo_ocorrencia: str
    descricao_ocorrencia: str
    foi_pago: bool


@dataclass(slots=True)
class ResultadoParseRetorno:
    """Resumo do parse de um arquivo de retorno."""

    total_linhas: int
    pagamentos: list[RetornoPagamento]
    pagos: int
    nao_pagos: int


def parsear_arquivo_retorno(conteudo: bytes) -> ResultadoParseRetorno:
    """Lê os Segmentos A de um arquivo de retorno CNAB 240.

    O parser é estrito quanto a:
    - Banco 136 (Unicred) nas posições 1-3
    - Tipo de registro 3 na posição 8
    - Segmento 'A' na posição 14

    Mas é tolerante a outras variações.

    Raises:
        LoteFormatoNaoReconhecidoError: arquivo vazio ou sem nenhum Segmento A
    """
    if not conteudo:
        raise LoteFormatoNaoReconhecidoError("Arquivo de retorno vazio")

    # Tenta latin-1 primeiro (encoding clássico CNAB), fallback utf-8
    try:
        texto = conteudo.decode("latin-1")
    except UnicodeDecodeError:
        texto = conteudo.decode("utf-8", errors="replace")

    linhas = [linha for linha in texto.split("\r\n") if linha.strip()]
    if not linhas:
        # Tenta também \n direto
        linhas = [linha for linha in texto.split("\n") if linha.strip()]

    pagamentos: list[RetornoPagamento] = []

    for linha in linhas:
        if len(linha) < 240:
            # Linha quebrada — pula
            continue

        if linha[:3] != "136":
            # Banco diferente da Unicred — provavelmente não é nosso formato
            continue

        if linha[7] != "3":
            # Não é registro de detalhe
            continue

        if linha[13] != "A":
            # Não é Segmento A (B trazem dados complementares)
            continue

        try:
            sequencial = int(linha[8:13])
        except ValueError:
            continue

        nome = linha[43:73].strip()
        id_documento = linha[73:93].strip()

        try:
            valor_centavos = int(linha[119:134])
        except ValueError:
            valor_centavos = 0

        # Códigos de ocorrência: posições 230-240 (10 chars), 5 grupos de 2
        codigos_brutos = linha[230:240]
        # Primeiro código (mais relevante)
        codigo = codigos_brutos[:2].strip().upper()

        descricao = CODIGOS_OCORRENCIA.get(codigo, f"Código {codigo}")
        foi_pago = codigo in CODIGOS_DE_SUCESSO

        pagamentos.append(
            RetornoPagamento(
                sequencial=sequencial,
                nome_favorecido=nome,
                valor_centavos=valor_centavos,
                id_documento=id_documento,
                codigo_ocorrencia=codigo,
                descricao_ocorrencia=descricao,
                foi_pago=foi_pago,
            )
        )

    if not pagamentos:
        raise LoteFormatoNaoReconhecidoError(
            "Nenhum Segmento A encontrado no arquivo de retorno. "
            "Verifique se é um arquivo .ret CNAB 240 da Unicred."
        )

    pagos = sum(1 for p in pagamentos if p.foi_pago)
    return ResultadoParseRetorno(
        total_linhas=len(linhas),
        pagamentos=pagamentos,
        pagos=pagos,
        nao_pagos=len(pagamentos) - pagos,
    )


__all__ = [
    "CODIGOS_DE_SUCESSO",
    "CODIGOS_OCORRENCIA",
    "ResultadoParseRetorno",
    "RetornoPagamento",
    "parsear_arquivo_retorno",
]
