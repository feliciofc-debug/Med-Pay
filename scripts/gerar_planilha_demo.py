"""Gera planilhas XLSX de demonstração para testar o MedPag.

Gera 2 arquivos:
  - planilha-hospital-santa-casa-novembro-2026.xlsx (45 médicos, 7 erros plantados)
  - planilha-clinica-vida-nova-novembro-2026.xlsx   (18 médicos, 3 erros plantados)

Os erros plantados são deliberados pra mostrar o semáforo do MedPag funcionando:
  - CPFs com 10 dígitos (zero perdido pelo Excel) → ⚠️ amarelo (sugere correção)
  - CPF com dígito verificador inválido → ❌ vermelho
  - Valor muito alto (suspeito) → ⚠️ amarelo
  - Linha duplicada (mesmo CPF + valor) → ⚠️ amarelo
  - Banco inexistente (código 999) → ❌ vermelho
  - Conta com formato impossível → ❌ vermelho

Uso:
    cd backend
    python ../scripts/gerar_planilha_demo.py
    # arquivos vão pra ../planilhas-demo/

Requer: pandas, openpyxl, validate-docbr (já em backend/requirements.txt)
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

try:
    import pandas as pd
    from validate_docbr import CPF
except ImportError:
    print("ERRO: instale as dependências do backend primeiro:")
    print("    cd backend && pip install -r requirements.txt")
    sys.exit(1)


# ============================================================
# Configuração
# ============================================================

NOMES_MEDICOS = [
    "DR ANTONIO CARLOS SILVA", "DRA BEATRIZ MARTINS COSTA",
    "DR CARLOS EDUARDO RIBEIRO", "DRA DANIELA OLIVEIRA SANTOS",
    "DR EDUARDO FERREIRA LIMA", "DRA FERNANDA RODRIGUES ALVES",
    "DR GUILHERME ALMEIDA SOUSA", "DRA HELENA TEIXEIRA DUARTE",
    "DR IGOR BARBOSA NUNES", "DRA JULIANA CARVALHO MELO",
    "DR KARLOS HENRIQUE PEIXOTO", "DRA LARA MENDES PEREIRA",
    "DR MARCOS VINICIUS BATISTA", "DRA NATALIA RAMOS GOMES",
    "DR OTAVIO MOREIRA CAMPOS", "DRA PATRICIA NUNES ROCHA",
    "DR QUEZIA FERREIRA MAIA", "DRA RAFAELA CARDOSO SOARES",
    "DR SERGIO LIMA AZEVEDO", "DRA TATIANA VIEIRA MACHADO",
    "DR UBIRAJARA GONCALVES PINTO", "DRA VANESSA DUARTE TAVARES",
    "DR WAGNER MENDES PRADO", "DRA XENIA BORGES FREITAS",
    "DR YURI CASTRO ARAUJO", "DRA ZILMA PIRES NASCIMENTO",
    "DR ANDRE LUIS MORAIS", "DRA BRUNA REZENDE FONSECA",
    "DR CESAR AUGUSTO MATOS", "DRA DIANA RIBEIRO TORRES",
    "DR ENRICO MORAES FIGUEIREDO", "DRA FABIANA LOPES BRITO",
    "DR GERALDO PAULA AGUIAR", "DRA HORTENCIA SANTOS CRUZ",
    "DR ISMAEL CAVALCANTE PIRES", "DRA JANAINA REIS BARROS",
    "DR KAUE GUEDES CARNEIRO", "DRA LIVIA PESSOA BENTO",
    "DR MURILO FRANCA BUENO", "DRA NEUSA AMORIM XAVIER",
    "DR OSVALDO PERES VIANA", "DRA PRISCILA ABREU SALES",
    "DR QUINTINO MARQUES PASSOS", "DRA RENATA SAMPAIO MELLO",
    "DR SAULO RIOS CORDEIRO", "DRA TANIA NEVES BITTENCOURT",
    "DR ULISSES TAVARES BORBA", "DRA VIRGINIA QUEIROZ ANDRADE",
]

# Códigos de banco válidos (FEBRABAN) — Unicred + alguns comuns
BANCOS_VALIDOS = ["136", "136", "136", "136", "136", "001", "237", "341", "104", "033"]


def gerar_cpf_valido() -> str:
    """Gera um CPF válido (11 dígitos com dígito verificador correto)."""
    cpf = CPF()
    return cpf.generate(mask=False)


def gerar_agencia() -> str:
    """Gera agência de 4 dígitos."""
    return f"{random.randint(1, 9999):04d}"


def gerar_conta() -> str:
    """Gera conta corrente realista."""
    return f"{random.randint(10000, 999999)}-{random.randint(0, 9)}"


def gerar_valor_normal() -> float:
    """Gera valor de pagamento típico de plantão médico (R$ 800 a R$ 12.000)."""
    return round(random.uniform(800, 12_000), 2)


# ============================================================
# Geração das planilhas
# ============================================================


def gerar_santa_casa() -> pd.DataFrame:
    """45 médicos com 7 erros plantados de propósito."""
    random.seed(42)
    linhas = []

    # 38 linhas perfeitas (verde)
    nomes_ok = NOMES_MEDICOS[:38]
    for nome in nomes_ok:
        linhas.append({
            "CPF": gerar_cpf_valido(),
            "Beneficiário": nome,
            "Banco": random.choice(BANCOS_VALIDOS),
            "Agência": gerar_agencia(),
            "Conta": gerar_conta(),
            "Valor": gerar_valor_normal(),
        })

    # Erro 1 e 2 — CPF com 10 dígitos (zero da frente perdido pelo Excel) → amarelo
    for nome in NOMES_MEDICOS[38:40]:
        cpf_full = gerar_cpf_valido()
        # Forçar CPF que começa com zero, depois remover o zero (simula o Excel)
        cpf_com_zero = "0" + cpf_full[1:]  # garante 11 dígitos começando com 0
        linhas.append({
            "CPF": cpf_com_zero.lstrip("0"),  # Excel removeu o zero → vira 10 dígitos
            "Beneficiário": nome,
            "Banco": "136",
            "Agência": gerar_agencia(),
            "Conta": gerar_conta(),
            "Valor": gerar_valor_normal(),
        })

    # Erro 3 — CPF com dígito verificador inválido → vermelho
    linhas.append({
        "CPF": "12345678901",  # CPF inválido (sequência falsa)
        "Beneficiário": NOMES_MEDICOS[40],
        "Banco": "136",
        "Agência": gerar_agencia(),
        "Conta": gerar_conta(),
        "Valor": gerar_valor_normal(),
    })

    # Erro 4 — valor suspeito (muito alto) → amarelo
    linhas.append({
        "CPF": gerar_cpf_valido(),
        "Beneficiário": NOMES_MEDICOS[41],
        "Banco": "136",
        "Agência": gerar_agencia(),
        "Conta": gerar_conta(),
        "Valor": 95_000.00,  # bem fora do padrão (R$ 800-12.000)
    })

    # Erro 5 — banco inexistente → vermelho
    linhas.append({
        "CPF": gerar_cpf_valido(),
        "Beneficiário": NOMES_MEDICOS[42],
        "Banco": "999",  # não existe na tabela FEBRABAN
        "Agência": gerar_agencia(),
        "Conta": gerar_conta(),
        "Valor": gerar_valor_normal(),
    })

    # Erro 6 e 7 — linha duplicada → amarelo
    duplicata = {
        "CPF": gerar_cpf_valido(),
        "Beneficiário": NOMES_MEDICOS[43],
        "Banco": "136",
        "Agência": gerar_agencia(),
        "Conta": gerar_conta(),
        "Valor": 3_500.00,
    }
    linhas.append(duplicata)
    linhas.append({**duplicata, "Beneficiário": NOMES_MEDICOS[43]})  # mesmo CPF+valor

    # Embaralha pra parecer mais real
    random.shuffle(linhas)

    return pd.DataFrame(linhas)


def gerar_vida_nova() -> pd.DataFrame:
    """18 médicos com 3 erros plantados — planilha menor pra mostrar variedade."""
    random.seed(99)
    linhas = []

    # 15 linhas perfeitas
    for nome in NOMES_MEDICOS[10:25]:
        linhas.append({
            "Documento": gerar_cpf_valido(),
            "Nome do Prestador": nome,
            "Cód Banco": random.choice(BANCOS_VALIDOS),
            "Agência": gerar_agencia(),
            "C/C": gerar_conta(),
            "Valor R$": gerar_valor_normal(),
        })

    # Erro 1 — CPF com 10 dígitos → amarelo
    linhas.append({
        "Documento": "1234567890",  # 10 dígitos
        "Nome do Prestador": NOMES_MEDICOS[25],
        "Cód Banco": "136",
        "Agência": gerar_agencia(),
        "C/C": gerar_conta(),
        "Valor R$": gerar_valor_normal(),
    })

    # Erro 2 — valor zero → vermelho
    linhas.append({
        "Documento": gerar_cpf_valido(),
        "Nome do Prestador": NOMES_MEDICOS[26],
        "Cód Banco": "136",
        "Agência": gerar_agencia(),
        "C/C": gerar_conta(),
        "Valor R$": 0,  # bloqueado
    })

    # Erro 3 — banco inexistente → vermelho
    linhas.append({
        "Documento": gerar_cpf_valido(),
        "Nome do Prestador": NOMES_MEDICOS[27],
        "Cód Banco": "888",
        "Agência": gerar_agencia(),
        "C/C": gerar_conta(),
        "Valor R$": gerar_valor_normal(),
    })

    random.shuffle(linhas)
    return pd.DataFrame(linhas)


# ============================================================
# Main
# ============================================================


def main() -> None:
    # Cria pasta de saída na raiz do projeto
    raiz = Path(__file__).resolve().parents[1]
    saida = raiz / "planilhas-demo"
    saida.mkdir(exist_ok=True)

    print("=" * 60)
    print("Gerando planilhas de demonstração para o MedPag")
    print("=" * 60)

    # Hospital Santa Casa
    df_santa = gerar_santa_casa()
    arq_santa = saida / "planilha-hospital-santa-casa-novembro-2026.xlsx"
    df_santa.to_excel(arq_santa, index=False, engine="openpyxl")
    print(f"[+] {arq_santa.name} — {len(df_santa)} linhas (7 erros plantados)")

    # Clínica Vida Nova
    df_vida = gerar_vida_nova()
    arq_vida = saida / "planilha-clinica-vida-nova-novembro-2026.xlsx"
    df_vida.to_excel(arq_vida, index=False, engine="openpyxl")
    print(f"[+] {arq_vida.name} — {len(df_vida)} linhas (3 erros plantados)")

    print()
    print("Arquivos prontos em:", saida)
    print()
    print("Erros plantados (Santa Casa):")
    print("  - 2x CPF com 10 dígitos (zero perdido pelo Excel) → amarelo")
    print("  - 1x CPF inválido (sequência falsa) → vermelho")
    print("  - 1x valor R$ 95.000 (suspeito) → amarelo")
    print("  - 1x banco código 999 (inexistente) → vermelho")
    print("  - 2x linha duplicada (mesmo CPF+valor) → amarelo")
    print()
    print("Erros plantados (Vida Nova):")
    print("  - 1x CPF com 10 dígitos → amarelo")
    print("  - 1x valor zero → vermelho")
    print("  - 1x banco código 888 → vermelho")
    print("=" * 60)


if __name__ == "__main__":
    main()
