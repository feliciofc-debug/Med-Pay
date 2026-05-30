"""Resolver de feature flags por cliente.

Filosofia:
    Cliente "assina" um plano (Inicial / Profissional / Avançado / Enterprise).
    O plano define features padrão num dict JSON. Cliente pode ter
    `features_override` que vence o que vem do plano. Resolver consulta
    override primeiro, depois plano, depois fallback hard-coded.

Uso típico no código:

    from app.services.feature_flags import cliente_tem_feature, get_limite

    if cliente_tem_feature(cliente, "pagamento.cnab"):
        gerar_cnab(...)

    limite = get_limite(cliente, "limite.pagamentos_mes")
    if limite and pagamentos_no_mes >= limite:
        raise LimitePlanoExcedidoError(...)

Catálogo único de features:
    FEATURES_DISPONIVEIS lista TODAS as chaves válidas. Quem adiciona
    feature nova precisa registrar aqui — assim frontend e backend
    falam a mesma língua e a tela de configuração consegue listar
    tudo dinamicamente.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.cliente import Cliente


class CategoriaFeature(str, Enum):
    """Agrupador visual pra tela de configuração."""

    PAGAMENTO = "Modalidades de Pagamento"
    MODULO = "Módulos"
    ANALISE = "Análise & Resultado"
    GESTAO = "Gestão & Compliance"
    LIMITE = "Limites de Uso"


@dataclass(frozen=True, slots=True)
class FeatureDef:
    """Definição de uma feature do catálogo."""

    chave: str
    nome: str
    descricao: str
    categoria: CategoriaFeature
    tipo: str  # "bool" ou "int" (limites)
    default: Any = False


# ============================================================
# Catálogo único — toda feature do sistema mora aqui
# ============================================================

FEATURES_DISPONIVEIS: tuple[FeatureDef, ...] = (
    # ---------- Modalidades de pagamento ----------
    FeatureDef(
        chave="pagamento.cnab",
        nome="Pagamento via CNAB 240",
        descricao="Gera arquivo CNAB 240 para envio ao banco emissor.",
        categoria=CategoriaFeature.PAGAMENTO,
        tipo="bool",
        default=False,
    ),
    FeatureDef(
        chave="pagamento.folha_municipal",
        nome="Integração com Folha Municipal",
        descricao="Exporta lançamentos para o sistema de RH/folha (Modo Relatório, API ou eSocial).",
        categoria=CategoriaFeature.PAGAMENTO,
        tipo="bool",
        default=False,
    ),
    FeatureDef(
        chave="pagamento.pix_direto",
        nome="PIX direto via API bancária",
        descricao="Envia PIX diretamente sem gerar CNAB (integração com API do banco).",
        categoria=CategoriaFeature.PAGAMENTO,
        tipo="bool",
        default=False,
    ),
    FeatureDef(
        chave="pagamento.execucao",
        nome="Execução de pagamento (ciclo completo)",
        descricao=(
            "O próprio tenant executa o pagamento ponta a ponta: cria/lança o "
            "lote, aprova e gera o CNAB (ou envia via API bancária). Ligado pra "
            "empresa de repasse e MedPag-SCP (operam sozinhas); desligado pra "
            "hospital, onde o BPO/Aprovador da MedPag fecha o ciclo."
        ),
        categoria=CategoriaFeature.PAGAMENTO,
        tipo="bool",
        default=False,
    ),
    FeatureDef(
        chave="pagamento.bolo_do_dia",
        nome="Bolo do Dia (rateio diário)",
        descricao="Modelo de pagamento por rateio diário entre profissionais (caso anestesistas).",
        categoria=CategoriaFeature.PAGAMENTO,
        tipo="bool",
        default=False,
    ),
    # ---------- Módulos ----------
    FeatureDef(
        chave="modulo.whatsapp_jarvis",
        nome="Jarvis WhatsApp",
        descricao="Assistente IA no WhatsApp pro admin do cliente.",
        categoria=CategoriaFeature.MODULO,
        tipo="bool",
        default=False,
    ),
    FeatureDef(
        chave="modulo.sentinela_vital",
        nome="MedPag Sentinela",
        descricao="Antifraude por sensores físicos (presença, vital signs, queda).",
        categoria=CategoriaFeature.MODULO,
        tipo="bool",
        default=False,
    ),
    FeatureDef(
        chave="modulo.equipe_flex",
        nome="Equipe Flex",
        descricao="Gestão de equipes médicas, escalas e fechamentos por equipe.",
        categoria=CategoriaFeature.MODULO,
        tipo="bool",
        default=False,
    ),
    FeatureDef(
        chave="modulo.crm_medico",
        nome="Autoatendimento do Médico (CRM)",
        descricao="Médico se autentica por CRM e lança próprios procedimentos.",
        categoria=CategoriaFeature.MODULO,
        tipo="bool",
        default=False,
    ),
    FeatureDef(
        chave="modulo.antifraude_qr",
        nome="Antifraude paciente (QR + selfie)",
        descricao="Paciente confirma procedimento via QR Code + selfie.",
        categoria=CategoriaFeature.MODULO,
        tipo="bool",
        default=False,
    ),
    FeatureDef(
        chave="modulo.dashboard_executivo",
        nome="Dashboard Executivo",
        descricao="Métricas avançadas: produtividade, ranking, exportações.",
        categoria=CategoriaFeature.MODULO,
        tipo="bool",
        default=False,
    ),
    FeatureDef(
        chave="modulo.contratos_hospital",
        nome="Gestão de Contratos Hospitalares",
        descricao="Contratos por modo (PRESTACAO, CESSAO, INTERMEDIACAO) e cobrança por modelo.",
        categoria=CategoriaFeature.MODULO,
        tipo="bool",
        default=False,
    ),
    # ---------- Análise & Resultado (Eixo 2: o que o tenant enxerga) ----------
    FeatureDef(
        chave="analise.lucro",
        nome="Apuração de Lucro / Margem",
        descricao=(
            "Mostra apuração de lucro e margem (receita − custos). Ligado pra "
            "empresa de repasse e MedPag-SCP; desligado pra hospital (que é gestão)."
        ),
        categoria=CategoriaFeature.ANALISE,
        tipo="bool",
        default=False,
    ),
    FeatureDef(
        chave="scp.apuracao",
        nome="Apuração SCP",
        descricao=(
            "Apuração de resultado da Sociedade em Conta de Participação por "
            "período (receita, custos, resultado distribuível)."
        ),
        categoria=CategoriaFeature.ANALISE,
        tipo="bool",
        default=False,
    ),
    FeatureDef(
        chave="scp.distribuicao",
        nome="Distribuição SCP",
        descricao=(
            "Distribuição do resultado aos médicos participantes da SCP "
            "(vira lote de repasse via banco tradicional)."
        ),
        categoria=CategoriaFeature.ANALISE,
        tipo="bool",
        default=False,
    ),
    # ---------- Gestão & Compliance (Eixo 2) ----------
    FeatureDef(
        chave="gestao.presenca_compliance",
        nome="Presença & Compliance",
        descricao=(
            "Gestão de presença/frequência e compliance trabalhista. Típico de "
            "hospital; pra empresa de repasse é add-on opcional."
        ),
        categoria=CategoriaFeature.GESTAO,
        tipo="bool",
        default=False,
    ),
    # ---------- Limites ----------
    FeatureDef(
        chave="limite.pagamentos_mes",
        nome="Pagamentos por mês",
        descricao="Máximo de pagamentos processados por mês (null = ilimitado).",
        categoria=CategoriaFeature.LIMITE,
        tipo="int",
        default=None,
    ),
    FeatureDef(
        chave="limite.usuarios",
        nome="Usuários ativos",
        descricao="Máximo de usuários ativos na conta (null = ilimitado).",
        categoria=CategoriaFeature.LIMITE,
        tipo="int",
        default=None,
    ),
    FeatureDef(
        chave="limite.clientes_filhos",
        nome="Clientes filhos (rede)",
        descricao="Quantas unidades/filiais a conta pode ter (null = ilimitado).",
        categoria=CategoriaFeature.LIMITE,
        tipo="int",
        default=None,
    ),
)


# Lookup rápido por chave
_BY_KEY: dict[str, FeatureDef] = {f.chave: f for f in FEATURES_DISPONIVEIS}


def get_feature_def(chave: str) -> FeatureDef | None:
    """Retorna a definição da feature do catálogo, ou None se chave inválida."""
    return _BY_KEY.get(chave)


def chaves_validas() -> set[str]:
    """Conjunto de todas as chaves de feature registradas."""
    return set(_BY_KEY.keys())


# ============================================================
# Resolver principal
# ============================================================


def resolver_feature(cliente: "Cliente", chave: str) -> Any:
    """Resolve o valor de uma feature pra um cliente específico.

    Ordem de prioridade:
        1. `cliente.features_override[chave]` (override pontual)
        2. `cliente.plano.features[chave]` (default do plano)
        3. `FeatureDef.default` (fallback do catálogo)
        4. None (chave fora do catálogo)
    """
    defin = _BY_KEY.get(chave)

    override = cliente.features_override or {}
    if chave in override:
        return override[chave]

    plano = cliente.plano
    if plano is not None and plano.features and chave in plano.features:
        return plano.features[chave]

    if defin is not None:
        return defin.default

    return None


def cliente_tem_feature(cliente: "Cliente", chave: str) -> bool:
    """Helper booleano: feature está ligada pro cliente?

    Funciona pra features tipo `bool`. Pra `int` (limites), use
    `get_limite`. Se a feature não existe no catálogo, retorna False
    em silêncio (fail-closed por segurança).
    """
    valor = resolver_feature(cliente, chave)
    return bool(valor)


def get_limite(cliente: "Cliente", chave: str) -> int | None:
    """Helper pra limites numéricos. None = ilimitado."""
    valor = resolver_feature(cliente, chave)
    if valor is None:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def features_resolvidas(cliente: "Cliente") -> dict[str, Any]:
    """Retorna o dict completo de features efetivas do cliente.

    Útil pro endpoint `/api/auth/me` retornar pro frontend num só
    payload — frontend usa pra esconder/mostrar UI.
    """
    return {f.chave: resolver_feature(cliente, f.chave) for f in FEATURES_DISPONIVEIS}


__all__ = [
    "CategoriaFeature",
    "FEATURES_DISPONIVEIS",
    "FeatureDef",
    "chaves_validas",
    "cliente_tem_feature",
    "features_resolvidas",
    "get_feature_def",
    "get_limite",
    "resolver_feature",
]
