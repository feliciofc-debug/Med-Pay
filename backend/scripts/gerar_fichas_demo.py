"""Gerador de fichas médicas demo (PNG) para simular upload de produção.

Gera 5 fichas no estilo "documento carimbado pelo hospital" que o
coordenador subiria pelo upload manual. Cada ficha tem cabeçalho do
hospital, tabela de plantões (médico + categoria + data + horas),
totais, e um carimbo simulado.

Os dados foram pensados pra exercitar o motor de cálculo:
    Hospital Santa Casa    → 18% MedPag (volume alto)
    Clínica Santa Luiza    → 27% MedPag (volume baixo)

Categorias e valor/hora hipotéticos:
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
class Plantao:
    medico: str
    crm: str
    categoria: str
    data: str
    hora_inicio: str
    hora_fim: str
    total_horas: float


@dataclass
class Ficha:
    nome_arquivo: str
    hospital: str
    cnpj_hospital: str
    competencia: str
    coordenador: str
    plantoes: list[Plantao]


# ---------------------------------------------------------------------------
# Fontes — tenta carregar fontes do sistema; cai pro default se não achar
# ---------------------------------------------------------------------------

def _carregar_fontes() -> dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]:
    fontes_candidatas = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    bold_candidatas = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "C:/Windows/Fonts/seguibl.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]

    def primeiro_existente(paths: list[str]) -> str | None:
        for p in paths:
            if os.path.exists(p):
                return p
        return None

    regular_path = primeiro_existente(fontes_candidatas)
    bold_path = primeiro_existente(bold_candidatas)

    if regular_path is None:
        return {
            "titulo": ImageFont.load_default(),
            "subtitulo": ImageFont.load_default(),
            "texto": ImageFont.load_default(),
            "pequeno": ImageFont.load_default(),
            "carimbo": ImageFont.load_default(),
        }

    return {
        "titulo": ImageFont.truetype(bold_path or regular_path, 36),
        "subtitulo": ImageFont.truetype(bold_path or regular_path, 22),
        "texto": ImageFont.truetype(regular_path, 18),
        "texto_bold": ImageFont.truetype(bold_path or regular_path, 18),
        "pequeno": ImageFont.truetype(regular_path, 14),
        "carimbo": ImageFont.truetype(bold_path or regular_path, 18),
    }


# ---------------------------------------------------------------------------
# Renderização
# ---------------------------------------------------------------------------

def _cabecalho(draw: ImageDraw.ImageDraw, ficha: Ficha, fontes: dict) -> int:
    # Faixa superior
    draw.rectangle(
        [(0, 0), (LARGURA, 18)],
        fill=COR_CABECALHO,
    )

    y = MARGEM
    draw.text(
        (MARGEM, y),
        ficha.hospital.upper(),
        fill=COR_CABECALHO,
        font=fontes["titulo"],
    )
    y += 50

    draw.text(
        (MARGEM, y),
        f"CNPJ: {ficha.cnpj_hospital}",
        fill=COR_TEXTO_FRACO,
        font=fontes["pequeno"],
    )
    y += 30

    # Linha divisora
    draw.line(
        [(MARGEM, y), (LARGURA - MARGEM, y)],
        fill=COR_CABECALHO,
        width=2,
    )
    y += 25

    draw.text(
        (MARGEM, y),
        "FICHA DE PLANTÕES MÉDICOS",
        fill=COR_TEXTO,
        font=fontes["subtitulo"],
    )
    y += 35

    draw.text(
        (MARGEM, y),
        f"Competência: {ficha.competencia}",
        fill=COR_TEXTO,
        font=fontes["texto"],
    )
    y += 25
    draw.text(
        (MARGEM, y),
        f"Coordenador: {ficha.coordenador}",
        fill=COR_TEXTO,
        font=fontes["texto"],
    )
    y += 40

    return y


def _tabela(
    draw: ImageDraw.ImageDraw,
    plantoes: list[Plantao],
    y_inicio: int,
    fontes: dict,
) -> int:
    # Cabeçalho da tabela
    cols = [
        ("Médico", 0, 320),
        ("CRM", 320, 100),
        ("Categoria", 420, 220),
        ("Data", 640, 110),
        ("Início", 750, 80),
        ("Fim", 830, 80),
        ("Horas", 910, 80),
    ]
    x_base = MARGEM

    altura_linha = 38
    y = y_inicio

    # Faixa do cabeçalho
    draw.rectangle(
        [(x_base, y), (x_base + 990, y + altura_linha)],
        fill=COR_CABECALHO,
    )
    for nome, dx, _ in cols:
        draw.text(
            (x_base + dx + 8, y + 10),
            nome,
            fill=(255, 255, 255),
            font=fontes["texto_bold"],
        )
    y += altura_linha

    # Linhas
    for idx, p in enumerate(plantoes):
        if idx % 2 == 1:
            draw.rectangle(
                [(x_base, y), (x_base + 990, y + altura_linha)],
                fill=(245, 245, 240),
            )
        valores = [
            p.medico,
            p.crm,
            p.categoria,
            p.data,
            p.hora_inicio,
            p.hora_fim,
            f"{p.total_horas:.1f}h",
        ]
        for (_, dx, _), val in zip(cols, valores):
            draw.text(
                (x_base + dx + 8, y + 10),
                val,
                fill=COR_TEXTO,
                font=fontes["texto"],
            )
        y += altura_linha

    # Linha de fechamento
    draw.line(
        [(x_base, y), (x_base + 990, y)],
        fill=COR_LINHA,
        width=1,
    )
    y += 15

    # Total
    total_horas = sum(p.total_horas for p in plantoes)
    draw.text(
        (x_base, y),
        f"Total de plantões: {len(plantoes)}     Horas totais: {total_horas:.1f}h",
        fill=COR_TEXTO,
        font=fontes["texto_bold"],
    )
    return y + 50


def _carimbo(draw: ImageDraw.ImageDraw, ficha: Ficha, y: int, fontes: dict) -> None:
    # Caixa do carimbo (em diagonal, estilo manuscrito)
    cx = LARGURA - MARGEM - 280
    cy = y + 40

    draw.rectangle(
        [(cx, cy), (cx + 260, cy + 130)],
        outline=COR_CARIMBO,
        width=3,
    )
    # Linha interna estilo selo
    draw.rectangle(
        [(cx + 6, cy + 6), (cx + 254, cy + 124)],
        outline=COR_CARIMBO,
        width=1,
    )

    draw.text(
        (cx + 18, cy + 14),
        "CONFERIDO E APROVADO",
        fill=COR_CARIMBO,
        font=fontes["carimbo"],
    )
    draw.text(
        (cx + 18, cy + 42),
        f"Em: {ficha.competencia}",
        fill=COR_CARIMBO,
        font=fontes["pequeno"],
    )
    draw.text(
        (cx + 18, cy + 64),
        f"{ficha.hospital[:30]}",
        fill=COR_CARIMBO,
        font=fontes["pequeno"],
    )
    draw.text(
        (cx + 18, cy + 86),
        "Diretoria Médica",
        fill=COR_CARIMBO,
        font=fontes["pequeno"],
    )
    draw.text(
        (cx + 18, cy + 104),
        ficha.coordenador,
        fill=COR_CARIMBO,
        font=fontes["pequeno"],
    )


def _rodape(draw: ImageDraw.ImageDraw, fontes: dict) -> None:
    y = ALTURA - 40
    draw.line(
        [(MARGEM, y - 10), (LARGURA - MARGEM, y - 10)],
        fill=COR_LINHA,
        width=1,
    )
    draw.text(
        (MARGEM, y),
        "Documento gerado pelo sistema interno do hospital — uso restrito",
        fill=COR_TEXTO_FRACO,
        font=fontes["pequeno"],
    )


def renderizar_ficha(ficha: Ficha, destino: Path) -> Path:
    img = Image.new("RGB", (LARGURA, ALTURA), COR_FUNDO)
    draw = ImageDraw.Draw(img)
    fontes = _carregar_fontes()

    y = _cabecalho(draw, ficha, fontes)
    y = _tabela(draw, ficha.plantoes, y, fontes)
    _carimbo(draw, ficha, y, fontes)
    _rodape(draw, fontes)

    caminho = destino / ficha.nome_arquivo
    img.save(caminho, format="PNG", dpi=(150, 150))
    return caminho


# ---------------------------------------------------------------------------
# Conjunto de fichas
# ---------------------------------------------------------------------------

_MEDICOS_BANCO = [
    ("Dr. Carlos Silva", "CRM 45821-RJ"),
    ("Dra. Marina Costa", "CRM 38492-RJ"),
    ("Dr. Roberto Lima", "CRM 51203-RJ"),
    ("Dra. Patrícia Mello", "CRM 27834-RJ"),
    ("Dr. Eduardo Pires", "CRM 49301-RJ"),
    ("Dra. Juliana Souza", "CRM 33872-RJ"),
    ("Dr. Felipe Andrade", "CRM 60411-RJ"),
    ("Dra. Camila Reis", "CRM 41209-RJ"),
    ("Enf. Sandra Vieira", "COREN 234897-RJ"),
    ("Enf. Marcos Oliveira", "COREN 198765-RJ"),
    ("Dr. Tiago Faria", "CRM 55720-RJ"),
    ("Dra. Beatriz Mota", "CRM 29384-RJ"),
]


def _gerar_plantao(
    medico: str,
    crm: str,
    categoria: str,
    dia: int,
    mes: str,
    inicio_hora: int,
    duracao_h: int,
) -> Plantao:
    fim_hora = (inicio_hora + duracao_h) % 24
    return Plantao(
        medico=medico,
        crm=crm,
        categoria=categoria,
        data=f"{dia:02d}/{mes}",
        hora_inicio=f"{inicio_hora:02d}:00",
        hora_fim=f"{fim_hora:02d}:00",
        total_horas=float(duracao_h),
    )


def _ficha_santa_casa_cirurgia(seed: int) -> Ficha:
    rng = random.Random(seed)
    plantoes: list[Plantao] = []
    medicos_cirurgia = [
        ("Dr. Carlos Silva", "CRM 45821-RJ", "Cirurgião"),
        ("Dr. Roberto Lima", "CRM 51203-RJ", "Cirurgião"),
        ("Dra. Marina Costa", "CRM 38492-RJ", "Anestesista"),
        ("Dra. Patrícia Mello", "CRM 27834-RJ", "Anestesista"),
    ]
    for dia in [3, 5, 8, 10, 12, 15, 17, 19, 22, 24]:
        m = rng.choice(medicos_cirurgia)
        plantoes.append(
            _gerar_plantao(m[0], m[1], m[2], dia, "06/2026", rng.choice([7, 13, 19]), 12),
        )
    return Ficha(
        nome_arquivo="01_santa_casa_cirurgia_jun2026.png",
        hospital="Hospital Santa Casa de Misericórdia",
        cnpj_hospital="33.481.804/0001-44",
        competencia="Junho / 2026",
        coordenador="Ana Paula Mendes — RH",
        plantoes=plantoes,
    )


def _ficha_santa_casa_uti(seed: int) -> Ficha:
    rng = random.Random(seed)
    plantoes: list[Plantao] = []
    medicos_uti = [
        ("Dr. Eduardo Pires", "CRM 49301-RJ", "Plantonista"),
        ("Dra. Juliana Souza", "CRM 33872-RJ", "Plantonista"),
        ("Dr. Felipe Andrade", "CRM 60411-RJ", "Plantonista"),
        ("Dra. Marina Costa", "CRM 38492-RJ", "Anestesista"),
    ]
    for dia in [1, 2, 4, 6, 7, 9, 11, 13, 14, 16, 18, 20]:
        m = rng.choice(medicos_uti)
        plantoes.append(
            _gerar_plantao(m[0], m[1], m[2], dia, "06/2026", rng.choice([7, 19]), 12),
        )
    return Ficha(
        nome_arquivo="02_santa_casa_uti_jun2026.png",
        hospital="Hospital Santa Casa de Misericórdia",
        cnpj_hospital="33.481.804/0001-44",
        competencia="Junho / 2026",
        coordenador="Ana Paula Mendes — RH",
        plantoes=plantoes,
    )


def _ficha_santa_casa_enfermagem(seed: int) -> Ficha:
    rng = random.Random(seed)
    plantoes: list[Plantao] = []
    enf = [
        ("Enf. Sandra Vieira", "COREN 234897-RJ", "Enfermeiro"),
        ("Enf. Marcos Oliveira", "COREN 198765-RJ", "Enfermeiro"),
    ]
    for dia in range(1, 21):
        m = rng.choice(enf)
        plantoes.append(
            _gerar_plantao(m[0], m[1], m[2], dia, "06/2026", rng.choice([7, 19]), 12),
        )
    return Ficha(
        nome_arquivo="03_santa_casa_enfermagem_jun2026.png",
        hospital="Hospital Santa Casa de Misericórdia",
        cnpj_hospital="33.481.804/0001-44",
        competencia="Junho / 2026",
        coordenador="Ana Paula Mendes — RH",
        plantoes=plantoes[:14],  # limita pra caber na página
    )


def _ficha_santa_luiza_clinica(seed: int) -> Ficha:
    rng = random.Random(seed)
    plantoes: list[Plantao] = []
    medicos = [
        ("Dr. Tiago Faria", "CRM 55720-RJ", "Plantonista"),
        ("Dra. Beatriz Mota", "CRM 29384-RJ", "Plantonista"),
        ("Dra. Camila Reis", "CRM 41209-RJ", "Anestesista"),
    ]
    for dia in [2, 5, 7, 9, 12, 14, 16, 19, 21, 23, 26, 28]:
        m = rng.choice(medicos)
        plantoes.append(
            _gerar_plantao(m[0], m[1], m[2], dia, "06/2026", rng.choice([8, 20]), 12),
        )
    return Ficha(
        nome_arquivo="04_clinica_santa_luiza_jun2026.png",
        hospital="Clínica Santa Luiza",
        cnpj_hospital="42.198.302/0001-09",
        competencia="Junho / 2026",
        coordenador="Felipe Rocha — Coord. Médico",
        plantoes=plantoes,
    )


def _ficha_santa_luiza_mai(seed: int) -> Ficha:
    rng = random.Random(seed)
    plantoes: list[Plantao] = []
    medicos = [
        ("Dr. Tiago Faria", "CRM 55720-RJ", "Plantonista"),
        ("Dra. Beatriz Mota", "CRM 29384-RJ", "Plantonista"),
        ("Dra. Camila Reis", "CRM 41209-RJ", "Anestesista"),
        ("Enf. Sandra Vieira", "COREN 234897-RJ", "Enfermeiro"),
    ]
    for dia in [3, 6, 8, 10, 13, 15, 17, 20, 22, 25, 27, 29]:
        m = rng.choice(medicos)
        plantoes.append(
            _gerar_plantao(m[0], m[1], m[2], dia, "05/2026", rng.choice([8, 20]), 12),
        )
    return Ficha(
        nome_arquivo="05_clinica_santa_luiza_mai2026.png",
        hospital="Clínica Santa Luiza",
        cnpj_hospital="42.198.302/0001-09",
        competencia="Maio / 2026",
        coordenador="Felipe Rocha — Coord. Médico",
        plantoes=plantoes,
    )


def montar_fichas() -> list[Ficha]:
    return [
        _ficha_santa_casa_cirurgia(1),
        _ficha_santa_casa_uti(2),
        _ficha_santa_casa_enfermagem(3),
        _ficha_santa_luiza_clinica(4),
        _ficha_santa_luiza_mai(5),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera fichas demo em PNG.")
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path.home() / "Desktop" / "fichas-demo",
        help="Pasta de saída. Default: Desktop/fichas-demo",
    )
    args = parser.parse_args()

    args.saida.mkdir(parents=True, exist_ok=True)
    fichas = montar_fichas()
    print(f"Gerando {len(fichas)} fichas em {args.saida} ...")
    for ficha in fichas:
        caminho = renderizar_ficha(ficha, args.saida)
        print(f"  [OK] {caminho.name}  ({len(ficha.plantoes)} plantoes)")
    print()
    print(f"Pronto! Pasta: {args.saida}")


if __name__ == "__main__":
    main()
