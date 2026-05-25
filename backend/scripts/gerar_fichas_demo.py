"""Gerador de fichas médicas demo (PNG) para simular upload de produção.

Gera 5 fichas no estilo "documento carimbado pelo hospital" que o
coordenador subiria pelo upload manual. Cada ficha tem cabeçalho do
hospital, lista de pagamentos formatada para o parser atual reconhecer
(CPF + valor + dados bancários por linha), totais, e carimbo simulado.

Os dados foram pensados pra exercitar o motor de cálculo:
    Hospital Santa Casa    → 18% MedPag (volume alto)
    Clínica Santa Luiza    → 27% MedPag (volume baixo)

Categorias e valor/hora (apenas pra calcular o valor — NÃO aparece
explicitamente na ficha em formato que ofuscaria o parser):
    Santa Casa:
        Cirurgião       R$ 250/h
        Anestesista     R$ 200/h
        Plantonista     R$ 120/h
        Enfermeiro      R$  45/h

    Clínica Santa Luiza:
        Plantonista     R$ 150/h
        Anestesista     R$ 220/h
        Enfermeiro      R$  55/h

Uso:
    python backend/scripts/gerar_fichas_demo.py
    python backend/scripts/gerar_fichas_demo.py --saida "C:\\Users\\usuario\\Desktop\\fichas-demo"
"""

from __future__ import annotations

import argparse
import os
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Layout A4 retrato em ~150 DPI
LARGURA = 1240
ALTURA = 1754
MARGEM = 80

# Paleta sóbria (estilo documento real)
COR_FUNDO = (252, 252, 248)       # creme claro
COR_TEXTO = (28, 28, 28)
COR_TEXTO_FRACO = (90, 90, 90)
COR_LINHA = (200, 200, 200)
COR_CABECALHO = (10, 50, 90)      # azul institucional
COR_CARIMBO = (140, 30, 30)       # vermelho carimbo


@dataclass
class Pagamento:
    nome: str
    cpf: str  # formato 000.000.000-00
    categoria: str
    horas: int
    valor_centavos: int
    banco_codigo: str | None = None
    agencia: str | None = None
    conta: str | None = None
    pix: str | None = None


@dataclass
class Ficha:
    nome_arquivo: str
    hospital: str
    cnpj_hospital: str
    competencia: str
    coordenador: str
    pagamentos: list[Pagamento]


# ============================================================
# CPF — gerador com checksum válido
# ============================================================


def _calc_dv(base: list[int]) -> int:
    pesos = list(range(len(base) + 1, 1, -1))
    soma = sum(d * p for d, p in zip(base, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def gerar_cpf_valido(rng: random.Random) -> str:
    base = [rng.randint(0, 9) for _ in range(9)]
    dv1 = _calc_dv(base)
    dv2 = _calc_dv(base + [dv1])
    digitos = base + [dv1, dv2]
    return f"{digitos[0]}{digitos[1]}{digitos[2]}.{digitos[3]}{digitos[4]}{digitos[5]}.{digitos[6]}{digitos[7]}{digitos[8]}-{digitos[9]}{digitos[10]}"


def gerar_dados_bancarios(rng: random.Random) -> tuple[str, str, str]:
    bancos = [("341", "Itaú"), ("237", "Bradesco"), ("001", "Banco do Brasil"), ("033", "Santander"), ("104", "Caixa")]
    codigo, _ = rng.choice(bancos)
    agencia = f"{rng.randint(1, 9999):04d}"
    conta = f"{rng.randint(10000, 999999)}-{rng.randint(0, 9)}"
    return codigo, agencia, conta


# ============================================================
# Fontes
# ============================================================


def _carregar_fontes() -> dict:
    candidatas_regular = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    candidatas_bold = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "C:/Windows/Fonts/seguibl.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    # Mono dá um look de "ficha digitada" e ajuda o OCR a separar campos
    candidatas_mono = [
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/cour.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]

    def primeiro(paths: list[str]) -> str | None:
        return next((p for p in paths if os.path.exists(p)), None)

    regular = primeiro(candidatas_regular)
    bold = primeiro(candidatas_bold)
    mono = primeiro(candidatas_mono) or regular

    if regular is None:
        return {
            k: ImageFont.load_default()
            for k in ("titulo", "subtitulo", "texto", "texto_bold", "mono", "mono_bold", "pequeno", "carimbo")
        }

    return {
        "titulo": ImageFont.truetype(bold or regular, 34),
        "subtitulo": ImageFont.truetype(bold or regular, 22),
        "texto": ImageFont.truetype(regular, 18),
        "texto_bold": ImageFont.truetype(bold or regular, 18),
        "mono": ImageFont.truetype(mono, 17),
        "mono_bold": ImageFont.truetype(mono, 18),
        "pequeno": ImageFont.truetype(regular, 14),
        "carimbo": ImageFont.truetype(bold or regular, 18),
    }


# ============================================================
# Renderização
# ============================================================


def _formatar_brl(centavos: int) -> str:
    reais = centavos / 100
    s = f"{reais:,.2f}"
    # vira padrão BR: 1,234.56 -> 1.234,56
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _cabecalho(draw: ImageDraw.ImageDraw, ficha: Ficha, fontes: dict) -> int:
    draw.rectangle([(0, 0), (LARGURA, 14)], fill=COR_CABECALHO)

    y = MARGEM
    draw.text((MARGEM, y), ficha.hospital.upper(), fill=COR_CABECALHO, font=fontes["titulo"])
    y += 46

    draw.text((MARGEM, y), f"CNPJ: {ficha.cnpj_hospital}", fill=COR_TEXTO_FRACO, font=fontes["pequeno"])
    y += 28

    draw.line([(MARGEM, y), (LARGURA - MARGEM, y)], fill=COR_CABECALHO, width=2)
    y += 22

    draw.text((MARGEM, y), "FICHA DE PLANTÕES MÉDICOS", fill=COR_TEXTO, font=fontes["subtitulo"])
    y += 32
    draw.text((MARGEM, y), f"Competência: {ficha.competencia}", fill=COR_TEXTO, font=fontes["texto"])
    y += 24
    draw.text((MARGEM, y), f"Coordenador: {ficha.coordenador}", fill=COR_TEXTO, font=fontes["texto"])
    y += 36
    return y


def _bloco_pagamento(
    draw: ImageDraw.ImageDraw,
    pag: Pagamento,
    y: int,
    fontes: dict,
) -> int:
    """Renderiza um único pagamento como 2 linhas:
    linha 1: NOME + CPF + horas + valor
    linha 2: dados bancários ou PIX
    Esse formato em texto contínuo (não tabela) ajuda o OCR a manter
    todos os campos juntos numa mesma linha lógica.
    """
    # Linha 1 — dados principais
    linha1 = (
        f"{pag.nome.upper():<32}  "
        f"CPF: {pag.cpf}   "
        f"{pag.categoria:<14}  "
        f"{pag.horas:>3}h   "
        f"{_formatar_brl(pag.valor_centavos):>14}"
    )
    draw.text((MARGEM, y), linha1, fill=COR_TEXTO, font=fontes["mono"])
    y += 22

    # Linha 2 — pagamento (banco ou PIX)
    if pag.pix:
        pgto = f"PIX: {pag.pix}"
    else:
        pgto = f"Banco: {pag.banco_codigo}   Ag: {pag.agencia}   C/C: {pag.conta}"
    draw.text((MARGEM + 26, y), pgto, fill=COR_TEXTO_FRACO, font=fontes["mono"])
    y += 28

    # Linha divisora fina
    draw.line([(MARGEM, y), (LARGURA - MARGEM, y)], fill=COR_LINHA, width=1)
    y += 12
    return y


def _rodape_ficha(draw: ImageDraw.ImageDraw, ficha: Ficha, y: int, fontes: dict) -> None:
    total = sum(p.valor_centavos for p in ficha.pagamentos)
    horas = sum(p.horas for p in ficha.pagamentos)
    y += 14
    draw.text(
        (MARGEM, y),
        f"Plantões pagos: {len(ficha.pagamentos)}     Horas totais: {horas}h     Total: {_formatar_brl(total)}",
        fill=COR_TEXTO,
        font=fontes["texto_bold"],
    )

    # Carimbo
    cx = LARGURA - MARGEM - 280
    cy = y + 60
    draw.rectangle([(cx, cy), (cx + 260, cy + 130)], outline=COR_CARIMBO, width=3)
    draw.rectangle([(cx + 6, cy + 6), (cx + 254, cy + 124)], outline=COR_CARIMBO, width=1)
    draw.text((cx + 18, cy + 14), "CONFERIDO E APROVADO", fill=COR_CARIMBO, font=fontes["carimbo"])
    draw.text((cx + 18, cy + 42), f"Em: {ficha.competencia}", fill=COR_CARIMBO, font=fontes["pequeno"])
    draw.text((cx + 18, cy + 64), ficha.hospital[:30], fill=COR_CARIMBO, font=fontes["pequeno"])
    draw.text((cx + 18, cy + 86), "Diretoria Médica", fill=COR_CARIMBO, font=fontes["pequeno"])
    draw.text((cx + 18, cy + 104), ficha.coordenador, fill=COR_CARIMBO, font=fontes["pequeno"])

    # Rodapé final
    yr = ALTURA - 40
    draw.line([(MARGEM, yr - 10), (LARGURA - MARGEM, yr - 10)], fill=COR_LINHA, width=1)
    draw.text(
        (MARGEM, yr),
        "Documento gerado pelo sistema interno do hospital — uso restrito",
        fill=COR_TEXTO_FRACO,
        font=fontes["pequeno"],
    )


def renderizar_ficha(ficha: Ficha, destino: Path) -> Path:
    img = Image.new("RGB", (LARGURA, ALTURA), COR_FUNDO)
    draw = ImageDraw.Draw(img)
    fontes = _carregar_fontes()

    y = _cabecalho(draw, ficha, fontes)
    draw.text((MARGEM, y), "PAGAMENTOS:", fill=COR_TEXTO, font=fontes["texto_bold"])
    y += 30
    for pag in ficha.pagamentos:
        y = _bloco_pagamento(draw, pag, y, fontes)
    _rodape_ficha(draw, ficha, y, fontes)

    caminho = destino / ficha.nome_arquivo
    img.save(caminho, format="PNG", dpi=(150, 150))
    return caminho


# ============================================================
# Conjunto de fichas demo
# ============================================================


_NOMES_MEDICOS = [
    "Carlos Silva",
    "Marina Costa",
    "Roberto Lima",
    "Patrícia Mello",
    "Eduardo Pires",
    "Juliana Souza",
    "Felipe Andrade",
    "Camila Reis",
    "Tiago Faria",
    "Beatriz Mota",
    "Rafael Cunha",
    "Letícia Barros",
    "Gustavo Vieira",
    "Larissa Antunes",
]

_NOMES_ENFERMEIROS = [
    "Sandra Vieira",
    "Marcos Oliveira",
    "Patrícia Soares",
    "André Ramos",
]


_VALOR_HORA_SANTA_CASA = {
    "Cirurgião": 25000,
    "Anestesista": 20000,
    "Plantonista": 12000,
    "Enfermeiro": 4500,
}

_VALOR_HORA_SANTA_LUIZA = {
    "Plantonista": 15000,
    "Anestesista": 22000,
    "Enfermeiro": 5500,
}


def _criar_pagamentos(
    rng: random.Random,
    medicos_categorias: list[tuple[str, str]],
    valor_hora: dict[str, int],
    horas_min: int,
    horas_max: int,
    pct_pix: float = 0.4,
) -> list[Pagamento]:
    pagamentos: list[Pagamento] = []
    for nome, categoria in medicos_categorias:
        horas = rng.randint(horas_min, horas_max)
        valor = horas * valor_hora[categoria]
        prefixo = "Dr. " if not nome.split()[-1].endswith("a") else "Dra. "
        if categoria == "Enfermeiro":
            prefixo = "Enf. "
        nome_full = f"{prefixo}{nome}"
        cpf = gerar_cpf_valido(rng)

        if rng.random() < pct_pix:
            pix = rng.choice([cpf, f"{nome.split()[0].lower()}.{nome.split()[-1].lower()}@email.com"])
            banco_codigo = agencia = conta = None
        else:
            banco_codigo, agencia, conta = gerar_dados_bancarios(rng)
            pix = None

        pagamentos.append(
            Pagamento(
                nome=nome_full,
                cpf=cpf,
                categoria=categoria,
                horas=horas,
                valor_centavos=valor,
                banco_codigo=banco_codigo,
                agencia=agencia,
                conta=conta,
                pix=pix,
            )
        )
    return pagamentos


def _ficha_santa_casa_cirurgia() -> Ficha:
    rng = random.Random(101)
    medicos = [
        ("Carlos Silva", "Cirurgião"),
        ("Roberto Lima", "Cirurgião"),
        ("Marina Costa", "Anestesista"),
        ("Patrícia Mello", "Anestesista"),
        ("Felipe Andrade", "Cirurgião"),
        ("Juliana Souza", "Anestesista"),
        ("Rafael Cunha", "Cirurgião"),
    ]
    pagamentos = _criar_pagamentos(rng, medicos, _VALOR_HORA_SANTA_CASA, 24, 72)
    return Ficha(
        nome_arquivo="01_santa_casa_cirurgia_jun2026.png",
        hospital="Hospital Santa Casa de Misericórdia",
        cnpj_hospital="33.481.804/0001-44",
        competencia="Junho / 2026",
        coordenador="Ana Paula Mendes — RH",
        pagamentos=pagamentos,
    )


def _ficha_santa_casa_uti() -> Ficha:
    rng = random.Random(102)
    medicos = [
        ("Eduardo Pires", "Plantonista"),
        ("Juliana Souza", "Plantonista"),
        ("Felipe Andrade", "Plantonista"),
        ("Camila Reis", "Plantonista"),
        ("Marina Costa", "Anestesista"),
        ("Letícia Barros", "Plantonista"),
        ("Gustavo Vieira", "Plantonista"),
    ]
    pagamentos = _criar_pagamentos(rng, medicos, _VALOR_HORA_SANTA_CASA, 36, 96)
    return Ficha(
        nome_arquivo="02_santa_casa_uti_jun2026.png",
        hospital="Hospital Santa Casa de Misericórdia",
        cnpj_hospital="33.481.804/0001-44",
        competencia="Junho / 2026",
        coordenador="Ana Paula Mendes — RH",
        pagamentos=pagamentos,
    )


def _ficha_santa_casa_enfermagem() -> Ficha:
    rng = random.Random(103)
    enf = [
        ("Sandra Vieira", "Enfermeiro"),
        ("Marcos Oliveira", "Enfermeiro"),
        ("Patrícia Soares", "Enfermeiro"),
        ("André Ramos", "Enfermeiro"),
    ]
    pagamentos = _criar_pagamentos(rng, enf, _VALOR_HORA_SANTA_CASA, 120, 200, pct_pix=0.6)
    return Ficha(
        nome_arquivo="03_santa_casa_enfermagem_jun2026.png",
        hospital="Hospital Santa Casa de Misericórdia",
        cnpj_hospital="33.481.804/0001-44",
        competencia="Junho / 2026",
        coordenador="Ana Paula Mendes — RH",
        pagamentos=pagamentos,
    )


def _ficha_santa_luiza_clinica() -> Ficha:
    rng = random.Random(104)
    medicos = [
        ("Tiago Faria", "Plantonista"),
        ("Beatriz Mota", "Plantonista"),
        ("Camila Reis", "Anestesista"),
        ("Larissa Antunes", "Plantonista"),
        ("Gustavo Vieira", "Anestesista"),
    ]
    pagamentos = _criar_pagamentos(rng, medicos, _VALOR_HORA_SANTA_LUIZA, 36, 84)
    return Ficha(
        nome_arquivo="04_clinica_santa_luiza_jun2026.png",
        hospital="Clínica Santa Luiza",
        cnpj_hospital="42.198.302/0001-09",
        competencia="Junho / 2026",
        coordenador="Felipe Rocha — Coord. Médico",
        pagamentos=pagamentos,
    )


def _ficha_santa_luiza_mai() -> Ficha:
    rng = random.Random(105)
    medicos = [
        ("Tiago Faria", "Plantonista"),
        ("Beatriz Mota", "Plantonista"),
        ("Camila Reis", "Anestesista"),
        ("Sandra Vieira", "Enfermeiro"),
        ("Larissa Antunes", "Plantonista"),
    ]
    pagamentos = _criar_pagamentos(rng, medicos, _VALOR_HORA_SANTA_LUIZA, 24, 72)
    return Ficha(
        nome_arquivo="05_clinica_santa_luiza_mai2026.png",
        hospital="Clínica Santa Luiza",
        cnpj_hospital="42.198.302/0001-09",
        competencia="Maio / 2026",
        coordenador="Felipe Rocha — Coord. Médico",
        pagamentos=pagamentos,
    )


def montar_fichas() -> list[Ficha]:
    return [
        _ficha_santa_casa_cirurgia(),
        _ficha_santa_casa_uti(),
        _ficha_santa_casa_enfermagem(),
        _ficha_santa_luiza_clinica(),
        _ficha_santa_luiza_mai(),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera fichas demo em PNG.")
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path.home() / "Desktop" / "fichas-demo",
        help="Pasta de saida. Default: Desktop/fichas-demo",
    )
    args = parser.parse_args()

    args.saida.mkdir(parents=True, exist_ok=True)
    fichas = montar_fichas()
    print(f"Gerando {len(fichas)} fichas em {args.saida} ...")
    for ficha in fichas:
        caminho = renderizar_ficha(ficha, args.saida)
        total = sum(p.valor_centavos for p in ficha.pagamentos) / 100
        print(
            f"  [OK] {caminho.name}  ({len(ficha.pagamentos)} pagamentos, R$ {total:,.2f})"
        )
    print()
    print(f"Pronto! Pasta: {args.saida}")


if __name__ == "__main__":
    main()
