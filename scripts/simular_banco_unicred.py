"""Simula a resposta da Unicred ao receber uma remessa CNAB 240.

Lê o arquivo .rem (remessa) que o MedPag gerou e produz um arquivo .ret
(retorno) com códigos de ocorrência realistas — alguns pagamentos "aceitos"
e alguns "rejeitados", simulando o comportamento de um banco de verdade.

ATENÇÃO: este script NÃO conversa com a Unicred real. Ele é puramente
local — pra testar o ciclo completo sem precisar de banco e sem mover
dinheiro de verdade.

Distribuição de respostas (configurável):
  - 92% → BD (pago com sucesso)
  -  4% → AJ (saldo insuficiente)
  -  2% → AE (conta favorecido inválida)
  -  2% → AK (conta inexistente)

Uso:
    python scripts/simular_banco_unicred.py CAMINHO_DO_ARQUIVO.rem

    # Variações:
    python scripts/simular_banco_unicred.py arquivo.rem --saida retorno.ret
    python scripts/simular_banco_unicred.py arquivo.rem --taxa-falha 0.20
    python scripts/simular_banco_unicred.py arquivo.rem --tudo-pago
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime
from pathlib import Path

# ============================================================
# Códigos de ocorrência (FEBRABAN)
# ============================================================

CODIGOS_SUCESSO = ["BD"]
CODIGOS_FALHA = [
    ("AJ", 0.50),  # saldo insuficiente — 50% das falhas
    ("AE", 0.25),  # conta favorecido inválida — 25%
    ("AK", 0.25),  # conta inexistente — 25%
]


def _escolher_codigo(taxa_falha: float, tudo_pago: bool) -> str:
    """Decide se o pagamento é aceito ou rejeitado, e qual o código."""
    if tudo_pago:
        return "BD"

    if random.random() > taxa_falha:
        return "BD"

    # Escolhe um código de falha conforme distribuição
    r = random.random()
    acumulado = 0.0
    for codigo, peso in CODIGOS_FALHA:
        acumulado += peso
        if r <= acumulado:
            return codigo
    return CODIGOS_FALHA[-1][0]


def _processar_linha(linha: str, taxa_falha: float, tudo_pago: bool) -> str:
    """Transforma uma linha de remessa em linha de retorno.

    Estratégia: o retorno tem o mesmo layout da remessa, mas:
      - posição 143 do header de arquivo é '2' (retorno) em vez de '1' (remessa)
      - nos Segmentos A (registro tipo 3, segmento A), as posições 230-240
        carregam o código de ocorrência (10 chars: 5 grupos de 2)
    """
    if len(linha) < 240:
        return linha

    # Header de arquivo: muda o flag de remessa pra retorno
    if linha[7] == "0":  # tipo registro 0 = header arquivo
        return linha[:142] + "2" + linha[143:]

    # Segmento A (registro tipo 3, segmento A na pos 14)
    if linha[7] == "3" and linha[13] == "A":
        codigo = _escolher_codigo(taxa_falha, tudo_pago)
        # Posições 230-240 (10 chars) — primeiro grupo é o código principal
        # Padrão FEBRABAN: 5 ocorrências de 2 chars cada
        codigo_field = (codigo + " " * 8)[:10]  # codigo + 8 espaços = 10 chars
        return linha[:230] + codigo_field

    # Outras linhas (header lote, segmento B, trailer lote, trailer arq):
    # mantém como está (banco devolve com poucas mudanças)
    return linha


def simular_retorno(
    rem_bytes: bytes,
    taxa_falha: float = 0.08,
    tudo_pago: bool = False,
    seed: int | None = None,
) -> bytes:
    """Gera o conteúdo .ret a partir do .rem.

    Args:
        rem_bytes: conteúdo do arquivo .rem
        taxa_falha: fração de pagamentos que serão rejeitados (0.0-1.0)
        tudo_pago: se True, força 100% de aprovação (ignora taxa_falha)
        seed: semente do random para reprodutibilidade (opcional)
    """
    if seed is not None:
        random.seed(seed)

    try:
        texto = rem_bytes.decode("latin-1")
    except UnicodeDecodeError:
        texto = rem_bytes.decode("utf-8", errors="replace")

    # CNAB usa \r\n entre linhas
    linhas = texto.split("\r\n") if "\r\n" in texto else texto.split("\n")

    novas_linhas = [_processar_linha(linha, taxa_falha, tudo_pago) for linha in linhas]

    return "\r\n".join(novas_linhas).encode("latin-1")


# ============================================================
# CLI
# ============================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulador do banco Unicred — lê remessa CNAB e gera retorno",
    )
    parser.add_argument(
        "arquivo_rem",
        type=Path,
        help="Caminho do arquivo .rem que o MedPag gerou",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=None,
        help="Caminho do arquivo .ret a gerar (default: mesmo nome do .rem com .ret)",
    )
    parser.add_argument(
        "--taxa-falha",
        type=float,
        default=0.08,
        help="Fração de pagamentos que serão rejeitados (0.0-1.0). Default: 0.08 (8%%)",
    )
    parser.add_argument(
        "--tudo-pago",
        action="store_true",
        help="Força 100%% de aprovação (ignora --taxa-falha)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Semente do random para resultados reproduzíveis (ex: 42)",
    )

    args = parser.parse_args()

    if not args.arquivo_rem.exists():
        print(f"ERRO: arquivo não encontrado: {args.arquivo_rem}")
        sys.exit(1)

    arq_saida = args.saida or args.arquivo_rem.with_suffix(".ret")

    print("=" * 60)
    print("Simulador Unicred — gerando retorno")
    print("=" * 60)
    print(f"  Entrada:    {args.arquivo_rem}")
    print(f"  Saída:      {arq_saida}")
    print(f"  Taxa falha: {args.taxa_falha:.1%}")
    print(f"  Tudo pago:  {args.tudo_pago}")
    print()

    rem_bytes = args.arquivo_rem.read_bytes()
    ret_bytes = simular_retorno(
        rem_bytes,
        taxa_falha=args.taxa_falha,
        tudo_pago=args.tudo_pago,
        seed=args.seed,
    )

    arq_saida.write_bytes(ret_bytes)

    # Estatística simples — conta os códigos
    texto_ret = ret_bytes.decode("latin-1")
    linhas = texto_ret.split("\r\n")
    pagos = 0
    falhas: dict[str, int] = {}
    for linha in linhas:
        if len(linha) >= 240 and linha[7] == "3" and linha[13] == "A":
            codigo = linha[230:232].strip().upper()
            if codigo == "BD":
                pagos += 1
            else:
                falhas[codigo] = falhas.get(codigo, 0) + 1

    print(f"Resultado da simulação:")
    print(f"  ✓ Pagos:    {pagos}")
    if falhas:
        for codigo, qtd in sorted(falhas.items()):
            nome = {"AJ": "saldo insuficiente", "AE": "conta inválida",
                    "AK": "conta inexistente"}.get(codigo, codigo)
            print(f"  ✗ {codigo} ({nome}): {qtd}")
    else:
        print(f"  ✗ Falhas: 0")
    print()
    print(f"[OK] arquivo .ret gerado: {arq_saida}")
    print()
    print("Próximo passo: faça upload deste .ret no MedPag")
    print("  (Dashboard → abrir lote → 'Subir retorno do banco')")
    print(f"Timestamp simulação: {datetime.now().isoformat()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
