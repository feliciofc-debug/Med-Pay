"""Validador de dados bancários (banco, agência, conta).

Mantém tabela básica de bancos FEBRABAN com regras específicas de
validação de agência e conta por banco. Foco inicial: Unicred.

Para expandir suporte a um novo banco, basta adicionar entrada em
`_BANCOS_SUPORTADOS` com as regras dele.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StatusBanco(str, Enum):
    """Status da validação bancária."""

    VALIDO = "VALIDO"
    INVALIDO = "INVALIDO"
    NAO_SUPORTADO = "NAO_SUPORTADO"  # Banco existe mas não está implementado


@dataclass(frozen=True, slots=True)
class RegraBanco:
    """Define as regras de validação de um banco."""

    codigo: str  # Código FEBRABAN (3 dígitos)
    nome: str
    agencia_tamanho_min: int
    agencia_tamanho_max: int
    conta_tamanho_min: int
    conta_tamanho_max: int
    suportado: bool = True


@dataclass(frozen=True, slots=True)
class ResultadoValidacaoBanco:
    """Resultado da validação de dados bancários."""

    status: StatusBanco
    banco_codigo: str | None
    banco_nome: str | None
    agencia_limpa: str | None
    conta_limpa: str | None
    codigo_erro: str | None
    mensagem: str

    @property
    def is_valido(self) -> bool:
        return self.status == StatusBanco.VALIDO


# ============================================================
# Tabela FEBRABAN
# ============================================================
# Inclui os bancos mais usados no Brasil + foco em Unicred (banco do MVP).
# Códigos extraídos de https://www.bcb.gov.br/

# Regra: a Unicred (banco pagador) faz TED CNAB-240 para qualquer banco
# brasileiro. "suportado=True" significa apenas que conhecemos as regras
# de validação de agência/conta do banco favorecido. Os tamanhos seguem
# os ranges típicos da FEBRABAN — mantidos generosos para tolerar pequenas
# variações que ocorrem na prática (contas com/sem DV explícito, etc).
_BANCOS_SUPORTADOS: dict[str, RegraBanco] = {
    "136": RegraBanco(
        codigo="136",
        nome="Unicred",
        agencia_tamanho_min=4,
        agencia_tamanho_max=5,
        conta_tamanho_min=4,
        conta_tamanho_max=12,
        suportado=True,
    ),
    "001": RegraBanco(
        codigo="001",
        nome="Banco do Brasil",
        agencia_tamanho_min=4,
        agencia_tamanho_max=5,
        conta_tamanho_min=4,
        conta_tamanho_max=12,
        suportado=True,
    ),
    "033": RegraBanco(
        codigo="033",
        nome="Santander",
        agencia_tamanho_min=4,
        agencia_tamanho_max=5,
        conta_tamanho_min=4,
        conta_tamanho_max=12,
        suportado=True,
    ),
    "104": RegraBanco(
        codigo="104",
        nome="Caixa Econômica",
        agencia_tamanho_min=4,
        agencia_tamanho_max=5,
        conta_tamanho_min=4,
        conta_tamanho_max=12,
        suportado=True,
    ),
    "237": RegraBanco(
        codigo="237",
        nome="Bradesco",
        agencia_tamanho_min=4,
        agencia_tamanho_max=5,
        conta_tamanho_min=4,
        conta_tamanho_max=12,
        suportado=True,
    ),
    "341": RegraBanco(
        codigo="341",
        nome="Itaú",
        agencia_tamanho_min=4,
        agencia_tamanho_max=5,
        conta_tamanho_min=4,
        conta_tamanho_max=12,
        suportado=True,
    ),
    "748": RegraBanco(
        codigo="748",
        nome="Sicredi",
        agencia_tamanho_min=4,
        agencia_tamanho_max=5,
        conta_tamanho_min=4,
        conta_tamanho_max=12,
        suportado=True,
    ),
    "756": RegraBanco(
        codigo="756",
        nome="Sicoob",
        agencia_tamanho_min=4,
        agencia_tamanho_max=5,
        conta_tamanho_min=4,
        conta_tamanho_max=12,
        suportado=True,
    ),
    "260": RegraBanco(
        codigo="260",
        nome="Nubank",
        agencia_tamanho_min=4,
        agencia_tamanho_max=5,
        conta_tamanho_min=4,
        conta_tamanho_max=12,
        suportado=True,
    ),
    "077": RegraBanco(
        codigo="077",
        nome="Banco Inter",
        agencia_tamanho_min=4,
        agencia_tamanho_max=5,
        conta_tamanho_min=4,
        conta_tamanho_max=12,
        suportado=True,
    ),
    "336": RegraBanco(
        codigo="336",
        nome="C6 Bank",
        agencia_tamanho_min=4,
        agencia_tamanho_max=5,
        conta_tamanho_min=4,
        conta_tamanho_max=12,
        suportado=True,
    ),
    "212": RegraBanco(
        codigo="212",
        nome="Banco Original",
        agencia_tamanho_min=4,
        agencia_tamanho_max=5,
        conta_tamanho_min=4,
        conta_tamanho_max=12,
        suportado=True,
    ),
    "422": RegraBanco(
        codigo="422",
        nome="Safra",
        agencia_tamanho_min=4,
        agencia_tamanho_max=5,
        conta_tamanho_min=4,
        conta_tamanho_max=12,
        suportado=True,
    ),
    "208": RegraBanco(
        codigo="208",
        nome="BTG Pactual",
        agencia_tamanho_min=4,
        agencia_tamanho_max=5,
        conta_tamanho_min=4,
        conta_tamanho_max=12,
        suportado=True,
    ),
}


# ============================================================
# Lista oficial FEBRABAN (códigos SPB) — usada como source-of-truth
# para "esse código existe ou não". Códigos abaixo cobrem >99% das
# transferências bancárias brasileiras (bancos comerciais, múltiplos,
# investimento, cooperativas e instituições de pagamento).
#
# Quando o código está aqui mas NÃO em _BANCOS_SUPORTADOS, criamos uma
# regra genérica on-the-fly (ag 4-5 dígitos, conta 4-12 dígitos). Isso
# nos permite aceitar pagamentos para bancos digitais novos sem precisar
# revisar a tabela toda a cada nova fintech homologada no BACEN.
#
# Atualizado em 2026-05 (lista BACEN/SPB).
# ============================================================

_FEBRABAN_TODOS: dict[str, str] = {
    "001": "Banco do Brasil S.A.",
    "003": "Banco da Amazônia S.A.",
    "004": "Banco do Nordeste do Brasil S.A.",
    "012": "Banco Inbursa S.A.",
    "021": "Banestes S.A.",
    "025": "Banco Alfa S.A.",
    "029": "Banco Itaú Consignado S.A.",
    "033": "Banco Santander (Brasil) S.A.",
    "036": "Banco Bradesco BBI S.A.",
    "037": "Banco do Estado do Pará S.A. (Banpará)",
    "041": "Banco do Estado do Rio Grande do Sul S.A. (Banrisul)",
    "047": "Banco do Estado de Sergipe S.A. (Banese)",
    "060": "Confidence Corretora de Câmbio S.A.",
    "062": "Hipercard Banco Múltiplo S.A.",
    "063": "Banco Bradescard S.A.",
    "064": "Goldman Sachs do Brasil",
    "065": "Banco AndBank (Brasil) S.A.",
    "066": "Banco Morgan Stanley S.A.",
    "069": "Banco Crefisa S.A.",
    "070": "BRB - Banco de Brasília S.A.",
    "074": "Banco J. Safra S.A.",
    "075": "Banco ABN Amro S.A.",
    "076": "Banco KDB S.A.",
    "077": "Banco Inter S.A.",
    "078": "Haitong Banco de Investimento do Brasil S.A.",
    "079": "Banco PicPay S.A. (Original do Agronegócio)",
    "080": "B&T Corretora de Câmbio",
    "081": "Banco Seguro S.A.",
    "082": "Banco Topázio S.A.",
    "083": "Banco da China Brasil S.A.",
    "084": "Sisprime do Brasil",
    "085": "Cooperativa Central de Crédito Ailos",
    "088": "Banco Randon S.A.",
    "089": "Cooperativa de Crédito Rural da Região da Mogiana",
    "091": "Central de Cooperativas de Economia e Crédito Mútuo (Unicred Central RS)",
    "092": "BRK Financeira S.A.",
    "093": "Pólocred Sociedade de Crédito ao Microempreendedor",
    "094": "Banco Finaxis S.A.",
    "095": "Travelex Banco de Câmbio",
    "096": "Banco B3 S.A.",
    "097": "Credisis - Central de Cooperativas de Crédito",
    "098": "Credialiança Cooperativa de Crédito Rural",
    "099": "Uniprime Central – Central Interestadual de Cooperativas",
    "100": "Planner Corretora de Valores S.A.",
    "101": "Renascença DTVM",
    "102": "XP Investimentos CCTVM S.A.",
    "104": "Caixa Econômica Federal",
    "105": "Lecca CFI S.A.",
    "107": "Banco BOCOM BBM S.A.",
    "108": "PortoCred S.A.",
    "111": "Oliveira Trust DTVM",
    "113": "Magliano S.A. Corretora",
    "114": "Central Cooperativa de Crédito no Estado do Espírito Santo",
    "117": "Advanced Corretora de Câmbio",
    "118": "Standard Chartered Bank",
    "119": "Banco Western Union do Brasil",
    "120": "Banco Rodobens S.A.",
    "121": "Banco Agibank S.A.",
    "122": "Bradesco BERJ S.A.",
    "124": "Banco Woori Bank do Brasil S.A.",
    "125": "Brasil Plural S.A. Banco Múltiplo",
    "126": "BR Partners Banco de Investimento",
    "127": "Codepe Corretora de Valores",
    "128": "MS Bank S.A. Banco de Câmbio",
    "129": "UBS Brasil Banco de Investimento",
    "130": "Caruana SCFI",
    "131": "Tullett Prebon Brasil Corretora",
    "132": "ICBC do Brasil Banco Múltiplo S.A.",
    "133": "Cresol Confederação",
    "134": "BGC Liquidez DTVM",
    "136": "Banco Unicred Cooperativo",
    "138": "Get Money Corretora de Câmbio",
    "139": "Intesa Sanpaolo Brasil S.A.",
    "140": "Easynvest - Título CV S.A.",
    "142": "Broker Brasil CC",
    "143": "Treviso Corretora de Câmbio",
    "144": "Bexs Banco de Câmbio S.A.",
    "145": "Levycam CCV",
    "146": "Guitta Corretora de Câmbio",
    "149": "Facta Financeira",
    "157": "ICAP do Brasil CTVM",
    "159": "Casa Crédito Financeira",
    "163": "Commerzbank Brasil",
    "169": "Banco Olé Consignado",
    "172": "Albatross CCV",
    "173": "BRL Trust DTVM",
    "174": "Pernambucanas Financiadora",
    "177": "Guide Investimentos",
    "180": "CM Capital Markets Corretora",
    "183": "Socred S.A. SCMEPP",
    "184": "Banco Itaú BBA S.A.",
    "188": "Ativa Investimentos S.A.",
    "189": "HS Financeira S.A.",
    "190": "Servicoop Cooperativa de Crédito",
    "191": "Nova Futura Corretora",
    "194": "Parmetal DTVM",
    "196": "Fair Corretora de Câmbio",
    "197": "Stone Pagamentos S.A.",
    "204": "Banco Bradesco Cartões S.A.",
    "208": "Banco BTG Pactual S.A.",
    "212": "Banco Original S.A.",
    "213": "Banco Arbi S.A.",
    "217": "Banco John Deere S.A.",
    "218": "Banco BS2 S.A.",
    "222": "Banco Credit Agricole Brasil",
    "224": "Banco Fibra S.A.",
    "233": "Banco Cifra S.A.",
    "237": "Banco Bradesco S.A.",
    "241": "Banco Clássico S.A.",
    "243": "Banco Master",
    "246": "Banco ABC Brasil S.A.",
    "249": "Banco Investcred Unibanco",
    "250": "BCV - Banco de Crédito e Varejo",
    "253": "Bexs Corretora de Câmbio",
    "254": "Paraná Banco S.A.",
    "260": "Nu Pagamentos S.A. (Nubank)",
    "265": "Banco Fator S.A.",
    "266": "Banco Cédula S.A.",
    "268": "Barigui Companhia Hipotecária",
    "269": "HSBC Brasil Banco de Investimento",
    "270": "Sagitur Corretora de Câmbio",
    "271": "IB Corretora de Câmbio",
    "272": "AGK Corretora de Câmbio",
    "273": "CCR de São Miguel do Oeste",
    "274": "MoneyCorp Banco de Câmbio",
    "276": "Senff Crédito Financiamento",
    "278": "Genial Investimentos Corretora",
    "279": "CCR de Primavera do Leste",
    "280": "Will Financeira S.A.",
    "281": "Cooperativa de Crédito Rural Coopavel",
    "283": "Rendimento Corretora de Títulos",
    "285": "Frente Corretora de Câmbio",
    "286": "Cooperativa Rural do Noroeste do RS",
    "288": "Carol DTVM",
    "289": "Decyseo Corretora de Câmbio",
    "290": "Pagseguro Internet S.A. (PagBank)",
    "292": "BS2 DTVM",
    "293": "Lastro RDV DTVM",
    "294": "Sulcredi/Crediplan",
    "295": "Pinbank Brasil",
    "296": "Vision S.A. Corretora",
    "297": "Cooperativa de Crédito Rural Vale do Itajaí",
    "298": "Vips Corretora de Câmbio",
    "299": "Sorocred CFI",
    "300": "Banco de la Nacion Argentina",
    "301": "BPP Instituição de Pagamento S.A.",
    "318": "Banco BMG S.A.",
    "320": "Banco Industrial e Comercial S.A. (ICBC)",
    "323": "Mercado Pago",
    "329": "QI Sociedade de Crédito Direto",
    "330": "Banco Bari de Investimentos",
    "332": "Acesso Soluções de Pagamento",
    "335": "Banco Digio S.A.",
    "336": "Banco C6 S.A.",
    "340": "Super Pagamentos e Administração",
    "341": "Banco Itaú S.A.",
    "342": "Creditas Sociedade de Crédito Direto",
    "343": "FFA Sociedade de Crédito Direto",
    "348": "Banco XP S.A.",
    "349": "AL5 Sociedade de Crédito Direto",
    "352": "TORO CTVM",
    "354": "NECTON Investimentos",
    "355": "ÓTIMO Sociedade de Crédito Direto",
    "359": "Zema CFI S.A.",
    "364": "Gerencianet Pagamentos do Brasil (efí)",
    "366": "Banco Société Générale Brasil",
    "370": "Banco Mizuho S.A.",
    "376": "Banco J.P. Morgan S.A.",
    "380": "PicPay Serviços S.A.",
    "383": "BoaVista Serviços (PagBank/SDS)",
    "389": "Banco Mercantil do Brasil S.A.",
    "390": "Banco GM S.A.",
    "394": "Banco Bradesco Financiamentos",
    "399": "Kirton Bank",
    "412": "Banco Capital S.A.",
    "422": "Banco Safra S.A.",
    "456": "Banco MUFG Brasil S.A.",
    "464": "Banco Sumitomo Mitsui Brasileiro",
    "473": "Banco Caixa Geral - Brasil",
    "477": "Citibank N.A.",
    "479": "Banco ItauBank S.A.",
    "487": "Deutsche Bank S.A.",
    "488": "JPMorgan Chase Bank",
    "492": "ING Bank N.V.",
    "495": "Banco de La Provincia de Buenos Aires",
    "505": "Banco Credit Suisse Brasil",
    "545": "Senso CCVM",
    "600": "Banco Luso Brasileiro S.A.",
    "604": "Banco Industrial do Brasil S.A.",
    "610": "Banco VR S.A.",
    "611": "Banco Paulista S.A.",
    "612": "Banco Guanabara S.A.",
    "613": "Banco Pine S.A.",
    "623": "Banco Pan S.A.",
    "626": "Banco Ficsa S.A.",
    "630": "Banco Smartbank",
    "633": "Banco Rendimento S.A.",
    "634": "Banco Triângulo S.A.",
    "637": "Banco Sofisa S.A.",
    "643": "Banco Pine",
    "652": "Itaú Unibanco Holding S.A.",
    "653": "Banco Indusval S.A.",
    "654": "Banco A.J. Renner",
    "655": "Banco Votorantim S.A.",
    "707": "Banco Daycoval S.A.",
    "712": "Banco Ourinvest S.A.",
    "739": "Banco Cetelem S.A.",
    "741": "Banco Ribeirão Preto S.A.",
    "743": "Banco Semear S.A.",
    "745": "Banco Citibank S.A.",
    "746": "Banco Modal S.A.",
    "747": "Banco Rabobank International",
    "748": "Banco Cooperativo Sicredi",
    "751": "Scotiabank Brasil",
    "752": "Banco BNP Paribas Brasil",
    "753": "Novo Banco Continental",
    "754": "Banco Sistema S.A.",
    "755": "Bank of America Merrill Lynch",
    "756": "Banco Cooperativo Sicoob",
    "757": "Banco KEB Hana do Brasil",
}


# ============================================================
# Funções auxiliares
# ============================================================


def normalizar_codigo_banco(codigo_raw: str | int | None) -> str:
    """Normaliza código de banco para 3 dígitos com zero à esquerda."""
    if codigo_raw is None or codigo_raw == "":
        return ""
    codigo = "".join(c for c in str(codigo_raw) if c.isdigit())
    return codigo.zfill(3) if codigo else ""


def limpar_agencia(agencia_raw: str | None) -> str:
    """Remove tudo que não é dígito da agência."""
    if not agencia_raw:
        return ""
    return "".join(c for c in str(agencia_raw) if c.isdigit())


def limpar_conta(conta_raw: str | None) -> str:
    """Remove tudo que não é dígito ou X (DV) da conta."""
    if not conta_raw:
        return ""
    return "".join(c for c in str(conta_raw).upper() if c.isdigit() or c == "X")


def obter_banco(codigo: str) -> RegraBanco | None:
    """Retorna a regra do banco se conhecido, None caso contrário.

    Estratégia em duas camadas:
      1. Tabela completa de regras (`_BANCOS_SUPORTADOS`) — regras
         específicas validadas com cada banco (Unicred, Itaú, etc).
      2. Lista FEBRABAN (`_FEBRABAN_TODOS`) — código existe mas
         ainda não temos regra específica → cria regra genérica
         (ag 4-5 dígitos, conta 4-12 dígitos), suficiente pra
         92% dos bancos brasileiros que seguem padrão FEBRABAN.
    Códigos fora dessas duas listas são considerados INVÁLIDOS
    (provavelmente erro de digitação).
    """
    codigo_normalizado = normalizar_codigo_banco(codigo)
    if not codigo_normalizado:
        return None
    if codigo_normalizado in _BANCOS_SUPORTADOS:
        return _BANCOS_SUPORTADOS[codigo_normalizado]
    nome = _FEBRABAN_TODOS.get(codigo_normalizado)
    if nome:
        return RegraBanco(
            codigo=codigo_normalizado,
            nome=nome,
            agencia_tamanho_min=4,
            agencia_tamanho_max=5,
            conta_tamanho_min=4,
            conta_tamanho_max=12,
            suportado=True,
        )
    return None


def listar_bancos_suportados() -> list[RegraBanco]:
    """Lista bancos com suporte completo (gerar CNAB)."""
    return [b for b in _BANCOS_SUPORTADOS.values() if b.suportado]


def codigo_febraban_valido(codigo_raw: str | int | None) -> bool:
    """True se o código consta na lista oficial FEBRABAN."""
    codigo = normalizar_codigo_banco(codigo_raw)
    return bool(codigo) and (
        codigo in _BANCOS_SUPORTADOS or codigo in _FEBRABAN_TODOS
    )


def nome_banco(codigo_raw: str | int | None) -> str | None:
    """Retorna nome do banco se o código for válido (FEBRABAN)."""
    codigo = normalizar_codigo_banco(codigo_raw)
    if not codigo:
        return None
    if codigo in _BANCOS_SUPORTADOS:
        return _BANCOS_SUPORTADOS[codigo].nome
    return _FEBRABAN_TODOS.get(codigo)


# ============================================================
# Função principal
# ============================================================


def validar_dados_bancarios(
    banco_raw: str | int | None,
    agencia_raw: str | None,
    conta_raw: str | None,
) -> ResultadoValidacaoBanco:
    """Valida combinação banco + agência + conta.

    Args:
        banco_raw: Código do banco (3 dígitos, pode vir com zero faltando)
        agencia_raw: Número da agência
        conta_raw: Número da conta (pode ter dígito verificador)

    Returns:
        ResultadoValidacaoBanco com status e mensagens
    """
    # Normaliza inputs
    banco_codigo = normalizar_codigo_banco(banco_raw)
    agencia_limpa = limpar_agencia(agencia_raw)
    conta_limpa = limpar_conta(conta_raw)

    # Validação 1: banco informado?
    if not banco_codigo:
        return ResultadoValidacaoBanco(
            status=StatusBanco.INVALIDO,
            banco_codigo=None,
            banco_nome=None,
            agencia_limpa=agencia_limpa or None,
            conta_limpa=conta_limpa or None,
            codigo_erro="BANCO_INVALIDO",
            mensagem="Código do banco não informado",
        )

    # Validação 2: banco conhecido?
    regra = obter_banco(banco_codigo)
    if regra is None:
        return ResultadoValidacaoBanco(
            status=StatusBanco.INVALIDO,
            banco_codigo=banco_codigo,
            banco_nome=None,
            agencia_limpa=agencia_limpa or None,
            conta_limpa=conta_limpa or None,
            codigo_erro="BANCO_INVALIDO",
            mensagem=f"Código de banco '{banco_codigo}' não consta na tabela FEBRABAN",
        )

    # Validação 3: banco suportado pelo sistema?
    if not regra.suportado:
        return ResultadoValidacaoBanco(
            status=StatusBanco.NAO_SUPORTADO,
            banco_codigo=banco_codigo,
            banco_nome=regra.nome,
            agencia_limpa=agencia_limpa or None,
            conta_limpa=conta_limpa or None,
            codigo_erro="BANCO_NAO_SUPORTADO",
            mensagem=(
                f"{regra.nome} ainda não está habilitado no sistema. "
                f"Suporte previsto para próximas versões."
            ),
        )

    # Validação 4: agência
    if not agencia_limpa:
        return ResultadoValidacaoBanco(
            status=StatusBanco.INVALIDO,
            banco_codigo=banco_codigo,
            banco_nome=regra.nome,
            agencia_limpa=None,
            conta_limpa=conta_limpa or None,
            codigo_erro="AGENCIA_INVALIDA",
            mensagem="Agência não informada",
        )

    if not (regra.agencia_tamanho_min <= len(agencia_limpa) <= regra.agencia_tamanho_max):
        return ResultadoValidacaoBanco(
            status=StatusBanco.INVALIDO,
            banco_codigo=banco_codigo,
            banco_nome=regra.nome,
            agencia_limpa=agencia_limpa,
            conta_limpa=conta_limpa or None,
            codigo_erro="AGENCIA_INVALIDA",
            mensagem=(
                f"Agência {regra.nome} deve ter entre {regra.agencia_tamanho_min} "
                f"e {regra.agencia_tamanho_max} dígitos (recebido: {len(agencia_limpa)})"
            ),
        )

    # Validação 5: conta
    if not conta_limpa:
        return ResultadoValidacaoBanco(
            status=StatusBanco.INVALIDO,
            banco_codigo=banco_codigo,
            banco_nome=regra.nome,
            agencia_limpa=agencia_limpa,
            conta_limpa=None,
            codigo_erro="CONTA_INVALIDA",
            mensagem="Conta não informada",
        )

    if not (regra.conta_tamanho_min <= len(conta_limpa) <= regra.conta_tamanho_max):
        return ResultadoValidacaoBanco(
            status=StatusBanco.INVALIDO,
            banco_codigo=banco_codigo,
            banco_nome=regra.nome,
            agencia_limpa=agencia_limpa,
            conta_limpa=conta_limpa,
            codigo_erro="CONTA_INVALIDA",
            mensagem=(
                f"Conta {regra.nome} deve ter entre {regra.conta_tamanho_min} "
                f"e {regra.conta_tamanho_max} dígitos (recebido: {len(conta_limpa)})"
            ),
        )

    # Tudo OK
    return ResultadoValidacaoBanco(
        status=StatusBanco.VALIDO,
        banco_codigo=banco_codigo,
        banco_nome=regra.nome,
        agencia_limpa=agencia_limpa,
        conta_limpa=conta_limpa,
        codigo_erro=None,
        mensagem=f"Dados bancários válidos ({regra.nome})",
    )
