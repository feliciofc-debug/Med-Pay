"""Presets de modelos de negócio (a "engenharia" do mapa mental em código).

Cada modelo de negócio NÃO é código novo — é uma combinação dos 3 eixos:

    Eixo 1 (QUEM)  -> TipoCliente
    Eixo 2 (O QUE) -> features (reusa Plano.features / features_override)
    Eixo 3 (COMO)  -> ModoPagamento

Este módulo só DECLARA os defaults sugeridos por tipo de tenant. Ele não
toca no banco: quem cria/edita cliente (signup, admin) pode aplicar o
preset como ponto de partida e depois ajustar fino no `features_override`.

Regra de ouro: o menu/dashboard do frontend deriva das features
resolvidas — então mudar o preset aqui já reflete na navegação, sem
`if tipo == 'hospital'` espalhado pelo código.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.cliente import ModoPagamento, TipoCliente


@dataclass(frozen=True, slots=True)
class PresetNegocio:
    """Template de defaults pra um tipo de tenant."""

    tipo: TipoCliente
    nome: str
    descricao: str
    modo_pagamento: ModoPagamento
    # Features ligadas por padrão neste modelo. Chaves seguem o catálogo
    # em `feature_flags.FEATURES_DISPONIVEIS`.
    features: dict[str, Any] = field(default_factory=dict)


# ============================================================
# Os modelos do mapa mental, em código
# ============================================================

PRESETS: dict[TipoCliente, PresetNegocio] = {
    TipoCliente.HOSPITAL: PresetNegocio(
        tipo=TipoCliente.HOSPITAL,
        nome="Hospital / Clínica",
        descricao=(
            "Paga os próprios médicos. Dashboard de gestão (sem lucro), "
            "foco em presença e compliance."
        ),
        modo_pagamento=ModoPagamento.CNAB_BANCARIO,
        features={
            "pagamento.cnab": True,
            "modulo.whatsapp_jarvis": True,
            "gestao.presenca_compliance": True,
            "analise.lucro": False,
        },
    ),
    TipoCliente.EMPRESA_REPASSE: PresetNegocio(
        tipo=TipoCliente.EMPRESA_REPASSE,
        nome="Empresa de Repasse",
        descricao=(
            "Contrata a MedPag e administra vários hospitais (tenant pai). "
            "Vê lucro/margem; compliance é add-on."
        ),
        modo_pagamento=ModoPagamento.CNAB_BANCARIO,
        features={
            "pagamento.cnab": True,
            "modulo.whatsapp_jarvis": True,
            "modulo.contratos_hospital": True,
            "analise.lucro": True,
            "gestao.presenca_compliance": False,
        },
    ),
    TipoCliente.MEDPAG_REPASSE: PresetNegocio(
        tipo=TipoCliente.MEDPAG_REPASSE,
        nome="MedPag Repasse (SCP)",
        descricao=(
            "A própria MedPag operando o repasse como sócio ostensivo (SCP). "
            "Apura resultado e distribui aos médicos participantes."
        ),
        modo_pagamento=ModoPagamento.REPASSE_SCP,
        features={
            "pagamento.cnab": True,
            "modulo.whatsapp_jarvis": True,
            "analise.lucro": True,
            "scp.apuracao": True,
            "scp.distribuicao": True,
        },
    ),
    TipoCliente.ONG: PresetNegocio(
        tipo=TipoCliente.ONG,
        nome="ONG / Terceiro Setor",
        descricao="Perfil enxuto, foco em transparência e prestação de contas.",
        modo_pagamento=ModoPagamento.CNAB_BANCARIO,
        features={
            "pagamento.cnab": True,
            "analise.lucro": False,
        },
    ),
}


def get_preset(tipo: TipoCliente) -> PresetNegocio:
    """Retorna o preset de um tipo de tenant (HOSPITAL como fallback)."""
    return PRESETS.get(tipo, PRESETS[TipoCliente.HOSPITAL])


def features_do_preset(tipo: TipoCliente) -> dict[str, Any]:
    """Atalho: só o dict de features ligadas do preset (cópia)."""
    return dict(get_preset(tipo).features)


__all__ = ["PRESETS", "PresetNegocio", "features_do_preset", "get_preset"]
