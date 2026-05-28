"""Schemas Pydantic do módulo Planos + Features."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.plano import StatusAssinatura


# ============================================================
# Catálogo de features (read-only, vem do Python)
# ============================================================


class FeatureDefOut(BaseModel):
    """Definição de uma feature do catálogo."""

    chave: str
    nome: str
    descricao: str
    categoria: str
    tipo: str  # "bool" ou "int"
    default: Any = None


# ============================================================
# Plano
# ============================================================


class PlanoOut(BaseModel):
    """Plano comercial completo."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    nome: str
    descricao: str | None
    preco_mensal_centavos: int
    trial_dias: int
    features: dict[str, Any]
    publico: bool
    ordem: int
    ativo: bool


class PlanoResumoOut(BaseModel):
    """Versão enxuta — só o essencial pra UI listar."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    nome: str
    preco_mensal_centavos: int
    trial_dias: int


# ============================================================
# Cliente — extensão pra incluir plano + features
# ============================================================


class ClienteAssinaturaOut(BaseModel):
    """Estado de assinatura + features efetivas de um cliente.

    O resolver expande `features_override` em cima do plano e devolve
    o dict completo em `features_efetivas` pra simplificar o frontend.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    cnpj: str | None
    status_assinatura: StatusAssinatura
    trial_termina_em: datetime | None

    plano: PlanoResumoOut | None
    features_override: dict[str, Any]
    features_efetivas: dict[str, Any] = Field(
        default_factory=dict,
        description="Features resolvidas (override > plano > default).",
    )


class AtualizarPlanoClienteRequest(BaseModel):
    """Troca o plano de um cliente."""

    plano_id: UUID | None = Field(
        None, description="UUID do novo plano. None = remove plano."
    )
    iniciar_trial: bool = Field(
        False,
        description=(
            "Se True e o plano tem trial_dias > 0, seta trial_termina_em + "
            "muda status pra TRIAL. Caso contrário muda pra ATIVO."
        ),
    )


class AtualizarFeaturesOverrideRequest(BaseModel):
    """Atualiza overrides de feature de um cliente.

    Substitui o dict inteiro de overrides (não merge). Cliente que
    quiser "voltar pro padrão do plano" manda `{}`.

    Chaves precisam estar no catálogo `FEATURES_DISPONIVEIS` —
    validação acontece no endpoint.
    """

    features_override: dict[str, Any] = Field(
        default_factory=dict,
        description="Dict {chave: valor} com overrides. Chaves do catálogo.",
    )


class AtualizarStatusAssinaturaRequest(BaseModel):
    """Muda status comercial manualmente (ex: cancelar contrato)."""

    status_assinatura: StatusAssinatura
    trial_termina_em: datetime | None = None


__all__ = [
    "AtualizarFeaturesOverrideRequest",
    "AtualizarPlanoClienteRequest",
    "AtualizarStatusAssinaturaRequest",
    "ClienteAssinaturaOut",
    "FeatureDefOut",
    "PlanoOut",
    "PlanoResumoOut",
]
