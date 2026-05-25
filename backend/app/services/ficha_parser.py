"""Parser do texto extraído pelo OCR de uma ficha de plantão.

O OCR devolve texto bruto, geralmente com ruído (carimbos sobrepondo
linhas, tabelas que viram colunas mal alinhadas, abreviações). Este
módulo tenta extrair os campos estruturados que viram pagamentos:

    - CPF (validado pelo `validators.cpf`)
    - Nome
    - Valor (R$ ou cents)
    - Quantidade de plantões / horas (informativo)
    - Banco / agência / conta (se aparecerem)
    - Chave PIX (se aparecer)

Quando o parser não consegue inferir um campo, ele DEIXA EM BRANCO.
O aprovador completa na tela de revisão antes de virar lote.

Filosofia: melhor extrair 70% dos dados e o humano completar 30%
do que tentar ser esperto demais e errar silenciosamente.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.validators.cpf import limpar_cpf, validar_cpf

# ============================================================
# Padrões regex
# ============================================================

# CPF formatado ou não: 123.456.789-01 ou 12345678901
_CPF_REGEX = re.compile(r"\b(\d{3}\.?\d{3}\.?\d{3}-?\d{2})\b")

# Valor monetário brasileiro: R$ 1.234,56 / 1234,56 / R$ 1.234,00 / R$1234
_VALOR_REGEX = re.compile(
    r"R?\$?\s*"
    r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+\.\d{2}|\d{3,})",
    re.IGNORECASE,
)

# Quantidade de plantões: "4 plantões", "Plantões: 4", "4 PT"
_PLANTOES_REGEX = re.compile(
    r"(?:plant[oõ]es?\s*[:\-]?\s*)(\d{1,3})|"
    r"\b(\d{1,3})\s+plant[oõ]es?\b|"
    r"\b(\d{1,3})\s*PT\b",
    re.IGNORECASE,
)

# Horas: "48h", "48 horas", "Horas: 48"
_HORAS_REGEX = re.compile(
    r"(?:horas?\s*[:\-]?\s*)(\d{1,4})|"
    r"\b(\d{1,4})\s*h(?:oras?)?\b",
    re.IGNORECASE,
)

# Banco: "Banco 341", "Banco: 341 Itaú", "Cód: 001"
_BANCO_REGEX = re.compile(
    r"(?:banco|c[oó]d|cod\.?)\s*[:\-]?\s*(\d{1,3})", re.IGNORECASE
)

# Agência: "Ag 1234", "Agência 1234", "Ag.: 1234-5"
_AGENCIA_REGEX = re.compile(
    r"(?:ag(?:[eê]ncia)?\.?)\s*[:\-]?\s*(\d{3,5}(?:[-/]?\d)?)", re.IGNORECASE
)

# Conta: "C/C 12345-6", "Conta: 12345-6"
_CONTA_REGEX = re.compile(
    r"(?:c\.?[/.]?c\.?|conta)\s*[:\-]?\s*(\d{4,12}[-/]?\d)", re.IGNORECASE
)

# Chave PIX (heurística — match em CPF, email ou telefone após "pix")
_PIX_REGEX = re.compile(
    r"pix\s*[:\-]?\s*(\S+@\S+|\+?\d[\d.\-/\s]{6,})", re.IGNORECASE
)

# Cabeçalho: hospital, competência, coordenador
_HOSPITAL_REGEX = re.compile(
    r"(?:hospital|cl[ií]nica|institui[çc][aã]o)\s*[:\-]?\s*([^\n]+?)$",
    re.IGNORECASE | re.MULTILINE,
)
_COMPETENCIA_REGEX = re.compile(
    r"(?:compet[eê]ncia|m[eê]s\s*[/-]?\s*ano|refer[eê]ncia)\s*[:\-]?\s*"
    r"(\d{1,2}\s*[/\-]\s*\d{2,4}|[A-Za-zçãõéí]+\s*[/\-]?\s*\d{2,4})",
    re.IGNORECASE,
)
_COORDENADOR_REGEX = re.compile(
    r"(?:coordenador(?:a)?|respons[aá]vel)\s*[:\-]?\s*([^\n]+?)$",
    re.IGNORECASE | re.MULTILINE,
)

# Nomes em CAIXA ALTA são candidatos a nome do beneficiário (típico em fichas)
_NOME_UPPER_REGEX = re.compile(
    r"\b((?:DR\.?\s+|DRA\.?\s+)?(?:[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}\s+){1,5}"
    r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,})\b"
)


# ============================================================
# Resultado
# ============================================================


@dataclass(slots=True)
class LinhaExtraida:
    """Uma linha de pagamento candidata extraída da ficha."""

    cpf: str | None = None
    nome: str | None = None
    valor_centavos: int | None = None
    qtd_plantoes: int | None = None
    horas: int | None = None
    banco_codigo: str | None = None
    agencia: str | None = None
    conta: str | None = None
    chave_pix: str | None = None
    linha_origem: str = ""
    avisos: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpf": self.cpf,
            "nome": self.nome,
            "valor_centavos": self.valor_centavos,
            "qtd_plantoes": self.qtd_plantoes,
            "horas": self.horas,
            "banco_codigo": self.banco_codigo,
            "agencia": self.agencia,
            "conta": self.conta,
            "chave_pix": self.chave_pix,
            "linha_origem": self.linha_origem,
            "avisos": self.avisos,
        }


@dataclass(slots=True)
class ResultadoParse:
    linhas: list[LinhaExtraida]
    metadados: dict[str, Any]


# ============================================================
# Helpers
# ============================================================


def _valor_para_centavos(texto: str) -> int | None:
    """Converte string de valor para centavos.

    Aceita: "1.234,56", "1234,56", "1234.56", "350" (sem decimal → reais).
    Retorna None se não conseguir parsear.
    """
    s = texto.strip().replace("R$", "").replace("r$", "").strip()
    if not s:
        return None

    # 1.234,56 → padrão brasileiro
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") == 1 and len(s.split(".")[-1]) == 2:
        # 1234.56 → padrão americano com 2 decimais
        pass
    else:
        # "350" / "1234" → reais inteiros
        s = s.replace(".", "")
    try:
        valor_reais = float(s)
    except ValueError:
        return None
    if valor_reais < 0 or valor_reais > 1_000_000:
        return None
    return int(round(valor_reais * 100))


def _extrair_metadados(texto: str) -> dict[str, Any]:
    metadados: dict[str, Any] = {}

    if m := _HOSPITAL_REGEX.search(texto):
        valor = m.group(1).strip().rstrip(":").strip()
        if 3 <= len(valor) <= 200:
            metadados["hospital"] = valor

    if m := _COMPETENCIA_REGEX.search(texto):
        metadados["competencia"] = m.group(1).strip()

    if m := _COORDENADOR_REGEX.search(texto):
        valor = m.group(1).strip().rstrip(":").strip()
        if 3 <= len(valor) <= 200:
            metadados["coordenador"] = valor

    return metadados


def _extrair_de_linha(linha: str) -> LinhaExtraida | None:
    """Extrai campos de uma única linha de texto da ficha.

    A heurística: uma linha vira candidata se tiver pelo menos um CPF
    válido OU um valor monetário + um nome em caixa alta.
    """
    linha = linha.strip()
    if len(linha) < 5:
        return None

    extraida = LinhaExtraida(linha_origem=linha)

    # 1. CPF
    if m := _CPF_REGEX.search(linha):
        cpf_bruto = m.group(1)
        resultado = validar_cpf(cpf_bruto)
        if resultado.cpf_limpo and len(resultado.cpf_limpo) == 11:
            extraida.cpf = resultado.cpf_limpo
            if resultado.is_corrigivel and resultado.cpf_sugerido:
                extraida.avisos.append(
                    f"CPF possivelmente errado, sugestão: {resultado.cpf_sugerido}"
                )
            elif not resultado.is_valido:
                extraida.avisos.append(f"CPF inválido: {resultado.mensagem}")
        else:
            extraida.avisos.append("CPF não pôde ser limpo")

    # 2. Valor (pega o MAIOR valor da linha — geralmente o pagamento total)
    valores = []
    for m in _VALOR_REGEX.finditer(linha):
        cents = _valor_para_centavos(m.group(1))
        if cents and cents >= 100:  # ignora R$ 0,xx
            valores.append(cents)
    if valores:
        extraida.valor_centavos = max(valores)

    # 3. Nome — pega a maior sequência em CAIXA ALTA da linha,
    # mas remove tokens que são CPF/valores
    nome_candidato = None
    for m in _NOME_UPPER_REGEX.finditer(linha):
        candidato = m.group(1).strip()
        # Filtros: deve ter ao menos uma palavra com 3+ chars
        if any(len(p) >= 3 for p in candidato.split()):
            if not nome_candidato or len(candidato) > len(nome_candidato):
                nome_candidato = candidato
    if nome_candidato:
        extraida.nome = nome_candidato.title().strip()

    # 4. Plantões / horas
    if m := _PLANTOES_REGEX.search(linha):
        valor_str = next((g for g in m.groups() if g), None)
        if valor_str:
            try:
                extraida.qtd_plantoes = int(valor_str)
            except ValueError:
                pass

    if m := _HORAS_REGEX.search(linha):
        valor_str = next((g for g in m.groups() if g), None)
        if valor_str:
            try:
                horas = int(valor_str)
                if 1 <= horas <= 9999:
                    extraida.horas = horas
            except ValueError:
                pass

    # 5. Banco / agência / conta
    if m := _BANCO_REGEX.search(linha):
        extraida.banco_codigo = m.group(1).zfill(3)[:3]
    if m := _AGENCIA_REGEX.search(linha):
        extraida.agencia = m.group(1).replace("/", "-")
    if m := _CONTA_REGEX.search(linha):
        extraida.conta = m.group(1).replace("/", "-")

    # 6. PIX
    if m := _PIX_REGEX.search(linha):
        extraida.chave_pix = m.group(1).strip()

    # Critério mínimo pra considerar candidata:
    # tem CPF OU (nome + valor)
    tem_cpf = bool(extraida.cpf)
    tem_par = bool(extraida.nome and extraida.valor_centavos)
    if not (tem_cpf or tem_par):
        return None

    return extraida


def _consolidar_linhas_proximas(
    linhas: list[LinhaExtraida],
) -> list[LinhaExtraida]:
    """Junta linhas adjacentes que parecem pertencer ao mesmo registro.

    Regra: se uma linha tem CPF mas não tem nome (ou vice-versa), e a
    linha anterior tem o oposto, mergeamos. Não faz nada sofisticado:
    o aprovador valida na revisão.
    """
    consolidadas: list[LinhaExtraida] = []
    for atual in linhas:
        if not consolidadas:
            consolidadas.append(atual)
            continue

        anterior = consolidadas[-1]
        # Se o registro anterior está incompleto (sem CPF) e o atual
        # só tem CPF, fundimos.
        if not anterior.cpf and atual.cpf and not atual.nome and not anterior.nome:
            anterior.cpf = atual.cpf
            anterior.avisos.extend(atual.avisos)
            anterior.linha_origem += " | " + atual.linha_origem
            continue
        if anterior.cpf and not anterior.nome and atual.nome and not atual.cpf:
            anterior.nome = atual.nome
            anterior.avisos.extend(atual.avisos)
            anterior.linha_origem += " | " + atual.linha_origem
            continue

        consolidadas.append(atual)

    return consolidadas


def _deduplicar_por_cpf(
    linhas: list[LinhaExtraida],
) -> list[LinhaExtraida]:
    """Remove duplicatas pelo CPF (somando valores se repetir).

    Útil porque o OCR às vezes lê a mesma linha duas vezes (linhas
    duplas em tabelas).
    """
    por_cpf: dict[str, LinhaExtraida] = {}
    sem_cpf: list[LinhaExtraida] = []

    for linha in linhas:
        if not linha.cpf:
            sem_cpf.append(linha)
            continue
        if linha.cpf not in por_cpf:
            por_cpf[linha.cpf] = linha
        else:
            existente = por_cpf[linha.cpf]
            # Se valores forem iguais, é duplicata pura → ignora
            # Se forem diferentes, soma e avisa
            if (
                linha.valor_centavos
                and existente.valor_centavos
                and linha.valor_centavos != existente.valor_centavos
            ):
                existente.valor_centavos += linha.valor_centavos
                existente.avisos.append(
                    "CPF apareceu mais de uma vez, valores foram somados"
                )
            existente.linha_origem += " | " + linha.linha_origem

    return list(por_cpf.values()) + sem_cpf


# ============================================================
# API pública
# ============================================================


def parsear_ficha(texto_ocr: str) -> ResultadoParse:
    """Recebe texto bruto do OCR e devolve linhas estruturadas + metadados.

    Sempre retorna um `ResultadoParse` (mesmo que vazio). Erros não
    levantam exceção: o caller decide se ficha vazia é problema.
    """
    if not texto_ocr or not texto_ocr.strip():
        return ResultadoParse(linhas=[], metadados={})

    metadados = _extrair_metadados(texto_ocr)

    candidatas: list[LinhaExtraida] = []
    for linha in texto_ocr.splitlines():
        extraida = _extrair_de_linha(linha)
        if extraida:
            candidatas.append(extraida)

    candidatas = _consolidar_linhas_proximas(candidatas)
    candidatas = _deduplicar_por_cpf(candidatas)

    # Última limpeza: remover linhas claramente sem dados úteis
    final = [
        linha
        for linha in candidatas
        if linha.cpf or (linha.nome and linha.valor_centavos)
    ]

    return ResultadoParse(linhas=final, metadados=metadados)


__all__ = [
    "LinhaExtraida",
    "ResultadoParse",
    "limpar_cpf",  # re-export pra conveniência
    "parsear_ficha",
]
