"""Parser do texto extraído pelo OCR de uma ficha de plantão.

O OCR devolve texto bruto, geralmente com ruído (carimbos sobrepondo
linhas, tabelas que viram colunas mal alinhadas, abreviações, perda
de caixa alta). Este módulo tenta extrair os campos estruturados que
viram pagamentos:

    - CPF (validado pelo `validators.cpf`)
    - Nome
    - Valor (R$ ou cents)
    - Quantidade de plantões / horas (informativo)
    - Banco / agência / conta (se aparecerem)
    - Chave PIX (se aparecer)

Estratégia atual:
    1. Lê linha por linha e marca candidatas (linha COM cpf é "mãe",
       linha SÓ com banco/agência/conta é "continuação").
    2. Quando uma linha "mãe" não tem nome detectável dentro dela,
       tenta:
       a. Pegar tudo antes do CPF como possível nome (DR./DRA./ENF.
          + 2 a 5 palavras)
       b. Olhar a linha imediatamente anterior se for puramente texto.
    3. Faz merge das linhas de continuação (banco/agência/conta) com
       a linha-mãe imediatamente anterior.
    4. Deduplica por CPF.

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

# Valor monetário brasileiro: R$ 1.234,56 / 1234,56 / R$ 1.234,00.
# Exigimos vírgula decimal (formato BR) ou R$ explícito pra evitar
# confundir com agências, contas, ou pedaços de CPF/PIX.
_VALOR_REGEX_BR = re.compile(
    r"R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", re.IGNORECASE
)
_VALOR_REGEX_VIRGULA = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})(?![\d])"
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

# Linhas de continuação começam com banco/ag/conta/pix
_LINHA_CONTINUACAO_REGEX = re.compile(
    r"^\s*(?:banco|c[oó]d\.?|ag(?:[eê]ncia)?\.?|c\.?[/.]?c\.?|conta|pix)\s*[:\-]",
    re.IGNORECASE,
)

# Prefixos profissionais que aparecem antes do nome (case-insensitive)
_PREFIXO_PROFISSIONAL = re.compile(
    r"^(dr\.?|dra\.?|sr\.?|sra\.?|enf\.?|enfermeir[oa]|t[eé]cnic[oa])\s+",
    re.IGNORECASE,
)

# Token "candidato a nome": uma sequência de 2-6 palavras com letras
# (aceita acentos, hífen). Permite caixa alta OU baixa.
_NOME_REGEX_FLEX = re.compile(
    r"((?:dr\.?|dra\.?|sr\.?|sra\.?|enf\.?)\s+)?"
    r"([A-Za-zÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]{2,}"
    r"(?:[\s\-'][A-Za-zÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]{2,}){1,5})",
    re.IGNORECASE,
)

# Palavras-chave que NUNCA são nome (pra filtrar falsos positivos)
_PALAVRAS_BLACKLIST = {
    "cpf", "cnpj", "ag", "agencia", "agência", "conta", "banco", "pix",
    "hospital", "clinica", "clínica", "competencia", "competência",
    "coordenador", "coordenadora", "ficha", "plantoes", "plantões",
    "valor", "horas", "data", "inicio", "início", "fim", "categoria",
    "diretoria", "medica", "médica", "recibo", "responsavel", "responsável",
    "rh", "anestesista", "cirurgiao", "cirurgião", "plantonista", "enfermeiro",
    "enfermeira", "clinico", "clínico", "geral", "uti", "ps",
    "documento", "documentos", "uso", "restrito", "interno", "sistema",
    "total", "totais", "pagos", "pagamentos", "conferido", "aprovado",
    "junho", "julho", "agosto", "setembro", "outubro", "novembro",
    "dezembro", "janeiro", "fevereiro", "março", "marco", "abril", "maio",
}


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

    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") == 1 and len(s.split(".")[-1]) == 2:
        pass
    else:
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


def _candidato_nome_eh_valido(candidato: str) -> bool:
    """Filtra falsos positivos (cabeçalhos da ficha como 'CPF VALOR' etc.)."""
    candidato_limpo = candidato.strip()
    if len(candidato_limpo) < 5:
        return False
    palavras = candidato_limpo.lower().split()
    if not palavras:
        return False
    # Mais de metade das palavras é blacklist? não é nome.
    blacklisted = sum(1 for p in palavras if p.strip(".,:") in _PALAVRAS_BLACKLIST)
    if blacklisted >= max(1, len(palavras) // 2):
        return False
    # Pelo menos 2 palavras com 3+ letras
    if sum(1 for p in palavras if len(p) >= 3) < 2:
        return False
    return True


def _formatar_nome(candidato: str) -> str:
    """Normaliza pra 'Title Case' preservando prefixos comuns."""
    candidato = candidato.strip().rstrip(":,.;").strip()

    # Se começa com prefixo profissional, capitaliza separado
    m = _PREFIXO_PROFISSIONAL.match(candidato)
    prefixo = ""
    resto = candidato
    if m:
        prefixo = m.group(1).rstrip(".").capitalize() + ". "
        resto = candidato[m.end():]
    return (prefixo + resto.title()).strip()


def _extrair_nome_da_linha(linha: str, posicao_cpf: int = -1) -> str | None:
    """Tenta extrair nome — duas estratégias:

    1. Se tem CPF, pega o pedaço antes do CPF como candidato.
    2. Senão, pega o melhor match do regex flexível na linha inteira.
    """
    linha_strip = linha.strip()

    if posicao_cpf > 0:
        prefixo = linha_strip[:posicao_cpf]
        # Remove "CPF:" ou "CPF" no final do prefixo
        prefixo = re.sub(r"\bcpf\s*[:\-]?\s*$", "", prefixo, flags=re.IGNORECASE)
        prefixo = prefixo.strip().rstrip(":,.;").strip()

        if _candidato_nome_eh_valido(prefixo):
            return _formatar_nome(prefixo)

    # Tenta pelo regex flexível
    melhor: str | None = None
    for m in _NOME_REGEX_FLEX.finditer(linha):
        texto_full = m.group(0).strip()
        if _candidato_nome_eh_valido(texto_full):
            if not melhor or len(texto_full) > len(melhor):
                melhor = texto_full
    return _formatar_nome(melhor) if melhor else None


def _extrair_de_linha(linha: str) -> LinhaExtraida | None:
    """Extrai campos de uma única linha de texto da ficha.

    Retorna candidata se a linha tem:
        - CPF (linha "mãe"), ou
        - banco/agência/conta sem CPF (linha "continuação"), ou
        - nome + valor (linha completa sem CPF)
    """
    linha_original = linha
    linha = linha.strip()
    if len(linha) < 5:
        return None

    extraida = LinhaExtraida(linha_origem=linha)

    # Detecta se é linha de continuação (banco/ag/cc/pix puro).
    # Nessas linhas, qualquer CPF encontrado é chave PIX — não cpf do beneficiário.
    eh_continuacao = bool(_LINHA_CONTINUACAO_REGEX.match(linha))

    # 1. CPF (só se NÃO for linha de continuação PIX)
    posicao_cpf = -1
    if not eh_continuacao and (m := _CPF_REGEX.search(linha)):
        cpf_bruto = m.group(1)
        posicao_cpf = m.start()
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

    # 2. Valor (preferimos R$ explícito; senão, valor com vírgula decimal)
    # Importante: limpa CPFs da linha antes pra não capturar dígitos do CPF.
    linha_sem_cpf = _CPF_REGEX.sub(" ", linha)
    valores: list[int] = []
    for m in _VALOR_REGEX_BR.finditer(linha_sem_cpf):
        cents = _valor_para_centavos(m.group(1))
        if cents and cents >= 100:
            valores.append(cents)
    if not valores:
        for m in _VALOR_REGEX_VIRGULA.finditer(linha_sem_cpf):
            cents = _valor_para_centavos(m.group(1))
            if cents and cents >= 100:
                valores.append(cents)
    if valores:
        extraida.valor_centavos = max(valores)

    # 3. Nome
    extraida.nome = _extrair_nome_da_linha(linha, posicao_cpf)

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

    # Critérios pra ser candidata:
    # - tem CPF (linha "mãe"), ou
    # - tem banco/ag/conta/pix (linha "continuação"), ou
    # - tem nome + valor (registro completo sem cpf legível)
    tem_cpf = bool(extraida.cpf)
    tem_dado_bancario = bool(
        extraida.banco_codigo
        or extraida.agencia
        or extraida.conta
        or extraida.chave_pix
    )
    tem_par = bool(extraida.nome and extraida.valor_centavos)

    if not (tem_cpf or tem_dado_bancario or tem_par):
        return None

    return extraida


def _consolidar_linhas_proximas(
    linhas: list[LinhaExtraida],
) -> list[LinhaExtraida]:
    """Junta linhas adjacentes que pertencem ao mesmo registro.

    Casos cobertos:
        a. Linha-mãe com CPF mas sem nome + linha anterior puro texto
           que parece ser o nome → fundimos.
        b. Linha-mãe com CPF + linha seguinte só com dados bancários
           (banco/ag/cc/pix) → mergeamos os dados bancários na mãe.
        c. Linhas duplicadas com CPF aparecendo 2x sem outro registro
           no meio (ruído de OCR) — tratado em deduplicação.
    """
    consolidadas: list[LinhaExtraida] = []
    for atual in linhas:
        if not consolidadas:
            consolidadas.append(atual)
            continue

        anterior = consolidadas[-1]

        # CASO B: linha "filha" só com dados bancários — funde na mãe
        atual_so_bancario = (
            not atual.cpf
            and not atual.nome
            and not atual.valor_centavos
            and (
                atual.banco_codigo
                or atual.agencia
                or atual.conta
                or atual.chave_pix
            )
        )
        if atual_so_bancario:
            if anterior.banco_codigo is None and atual.banco_codigo:
                anterior.banco_codigo = atual.banco_codigo
            if anterior.agencia is None and atual.agencia:
                anterior.agencia = atual.agencia
            if anterior.conta is None and atual.conta:
                anterior.conta = atual.conta
            if anterior.chave_pix is None and atual.chave_pix:
                anterior.chave_pix = atual.chave_pix
            anterior.linha_origem += " | " + atual.linha_origem
            anterior.avisos.extend(atual.avisos)
            continue

        # CASO A: cpf sem nome + atual tem nome sem cpf → mantemos
        # (resolvido pela linha anterior ter pegado o nome via _extrair_nome_da_linha)
        if anterior.cpf and not anterior.nome and atual.nome and not atual.cpf:
            anterior.nome = atual.nome
            anterior.linha_origem += " | " + atual.linha_origem
            continue

        if not anterior.cpf and atual.cpf and not atual.nome and not anterior.nome:
            anterior.cpf = atual.cpf
            anterior.linha_origem += " | " + atual.linha_origem
            continue

        consolidadas.append(atual)

    return consolidadas


def _aplicar_lookback_de_nomes(
    candidatas: list[LinhaExtraida], todas_linhas: list[str]
) -> None:
    """Para linhas com CPF mas sem nome, tenta achar nome em linhas vizinhas.

    Olha a linha de origem da candidata no texto bruto, e checa as
    1-2 linhas anteriores. Se uma dessas linhas vizinhas tem um padrão
    nome (sem CPF), usa.
    """
    # Indexa as linhas brutas pra busca rápida
    indices: dict[str, int] = {}
    for idx, l in enumerate(todas_linhas):
        indices.setdefault(l.strip(), idx)

    for candidata in candidatas:
        if candidata.nome or not candidata.cpf:
            continue

        # Pega a primeira parte da linha_origem (pode ter sido fundida com " | ")
        chave = candidata.linha_origem.split(" | ")[0].strip()
        idx = indices.get(chave)
        if idx is None or idx == 0:
            continue

        # Olha 2 linhas anteriores
        for offset in (1, 2):
            if idx - offset < 0:
                break
            linha_anterior = todas_linhas[idx - offset].strip()
            if not linha_anterior:
                continue
            # Se a linha anterior tem CPF, é outro registro — para
            if _CPF_REGEX.search(linha_anterior):
                break
            nome = _extrair_nome_da_linha(linha_anterior)
            if nome:
                candidata.nome = nome
                candidata.linha_origem = linha_anterior + " | " + candidata.linha_origem
                break


def _deduplicar_por_cpf(
    linhas: list[LinhaExtraida],
) -> list[LinhaExtraida]:
    """Remove duplicatas pelo CPF.

    Quando o OCR lê a mesma linha duas vezes, valores idênticos
    são tratados como repetição (ignora). Valores diferentes são
    somados (com aviso) — ainda há chance de erro mas é defensivo.
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

    todas_linhas = texto_ocr.splitlines()
    candidatas: list[LinhaExtraida] = []
    for linha in todas_linhas:
        extraida = _extrair_de_linha(linha)
        if extraida:
            candidatas.append(extraida)

    candidatas = _consolidar_linhas_proximas(candidatas)
    _aplicar_lookback_de_nomes(candidatas, todas_linhas)
    candidatas = _deduplicar_por_cpf(candidatas)

    # Filtro final — descarta linhas só com banco/agência sem CPF nem nome+valor
    final = [
        linha
        for linha in candidatas
        if linha.cpf or (linha.nome and linha.valor_centavos)
    ]

    return ResultadoParse(linhas=final, metadados=metadados)


__all__ = [
    "LinhaExtraida",
    "ResultadoParse",
    "limpar_cpf",
    "parsear_ficha",
]
