"""Apuração e distribuição de resultado da SCP.

Coração do modelo MEDPAG_REPASSE: dado o resultado de um período
(receita − custos), calcula quanto cada médico participante recebe,
conforme a regra de cota de cada um.

A função principal `calcular_distribuicoes` é PURA (sem banco) — fácil de
testar. A camada async (`gerar_distribuicao`) carrega participantes,
chama o cálculo e persiste as linhas de distribuição.

Algoritmo (suporta regras mistas no mesmo período):
    1. Participantes PERCENTUAL_FIXO recebem `resultado * pct_bp/10000`.
    2. O que sobra (resultado − soma dos fixos) é rateado entre os
       participantes variáveis (PROPORCIONAL_SERVICO e POR_APORTE),
       proporcional à base de cada um (serviço no período / aporte).
    3. Arredondamento: o último participante variável absorve a sobra de
       centavos, garantindo que a soma feche exatamente.

Centavos sempre inteiros — nunca float pra dinheiro.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scp import (
    ApuracaoSCP,
    DistribuicaoSCP,
    ParticipanteSCP,
    RegraCota,
    StatusApuracaoSCP,
)


@dataclass(slots=True)
class LinhaDistribuicao:
    """Resultado do cálculo pra um participante (antes de persistir)."""

    participante_id: UUID
    beneficiario_id: UUID
    base_centavos: int
    percentual_aplicado_bp: int
    valor_centavos: int


def calcular_distribuicoes(
    *,
    resultado_centavos: int,
    participantes: list[ParticipanteSCP],
    bases_servico: dict[UUID, int] | None = None,
) -> list[LinhaDistribuicao]:
    """Calcula a distribuição do resultado entre os participantes.

    Args:
        resultado_centavos: resultado distribuível (receita − custos).
        participantes: participantes ativos no período.
        bases_servico: mapa beneficiario_id → valor de serviço no período
            (centavos), usado pelas cotas PROPORCIONAL_SERVICO. Quando
            ausente pra um participante proporcional, cai pra base 1
            (rateio igualitário entre os proporcionais).

    Returns:
        Uma linha por participante (mesmo que valor 0).
    """
    bases_servico = bases_servico or {}
    if resultado_centavos <= 0 or not participantes:
        return [
            LinhaDistribuicao(
                participante_id=p.id,
                beneficiario_id=p.beneficiario_id,
                base_centavos=0,
                percentual_aplicado_bp=0,
                valor_centavos=0,
            )
            for p in participantes
        ]

    fixos = [p for p in participantes if p.regra_cota == RegraCota.PERCENTUAL_FIXO]
    variaveis = [p for p in participantes if p.regra_cota != RegraCota.PERCENTUAL_FIXO]

    linhas: dict[UUID, LinhaDistribuicao] = {}

    # ---- 1. Cotas fixas ----
    total_fixo = 0
    for p in fixos:
        valor = (resultado_centavos * max(p.percentual_bp, 0)) // 10000
        total_fixo += valor
        linhas[p.id] = LinhaDistribuicao(
            participante_id=p.id,
            beneficiario_id=p.beneficiario_id,
            base_centavos=0,
            percentual_aplicado_bp=max(p.percentual_bp, 0),
            valor_centavos=valor,
        )

    # ---- 2. Rateio do que sobra entre os variáveis ----
    restante = max(resultado_centavos - total_fixo, 0)

    def _base(p: ParticipanteSCP) -> int:
        if p.regra_cota == RegraCota.POR_APORTE:
            return max(p.aporte_centavos, 0)
        # PROPORCIONAL_SERVICO: serviço do período (ou 1 = igualitário)
        return max(bases_servico.get(p.beneficiario_id, 1), 0)

    soma_bases = sum(_base(p) for p in variaveis)
    distribuido_var = 0
    for idx, p in enumerate(variaveis):
        base = _base(p)
        if soma_bases > 0:
            valor = (restante * base) // soma_bases
        else:
            valor = 0
        # último variável absorve a sobra de arredondamento
        if idx == len(variaveis) - 1:
            valor = restante - distribuido_var
        distribuido_var += valor
        pct_bp = (valor * 10000) // resultado_centavos if resultado_centavos else 0
        linhas[p.id] = LinhaDistribuicao(
            participante_id=p.id,
            beneficiario_id=p.beneficiario_id,
            base_centavos=base,
            percentual_aplicado_bp=pct_bp,
            valor_centavos=valor,
        )

    # mantém a ordem original dos participantes
    return [linhas[p.id] for p in participantes]


# ============================================================
# Camada async (carrega + persiste)
# ============================================================


async def participantes_ativos(
    db: AsyncSession, cliente_id: UUID, *, em: date | None = None
) -> list[ParticipanteSCP]:
    """Participantes ativos da SCP, opcionalmente vigentes numa data."""
    stmt = select(ParticipanteSCP).where(
        ParticipanteSCP.cliente_id == cliente_id,
        ParticipanteSCP.ativo.is_(True),
    )
    result = await db.execute(stmt)
    parts = list(result.scalars().all())
    if em is not None:
        parts = [
            p
            for p in parts
            if p.vigencia_inicio <= em
            and (p.vigencia_fim is None or p.vigencia_fim >= em)
        ]
    return parts


def fechar_resultado(apuracao: ApuracaoSCP) -> int:
    """Calcula e grava resultado = receita − custos. Não comita."""
    resultado = apuracao.receita_bruta_centavos - apuracao.custos_centavos
    apuracao.resultado_centavos = max(resultado, 0)
    apuracao.status = StatusApuracaoSCP.FECHADA
    return apuracao.resultado_centavos


async def gerar_distribuicao(
    db: AsyncSession,
    apuracao: ApuracaoSCP,
    *,
    bases_servico: dict[UUID, int] | None = None,
) -> list[DistribuicaoSCP]:
    """Gera (e persiste) as linhas de distribuição de uma apuração.

    Recalcula o resultado, busca os participantes ativos e materializa a
    distribuição. Limpa distribuições antigas (recálculo idempotente).
    Não comita — quem chama controla a transação.
    """
    fechar_resultado(apuracao)

    parts = await participantes_ativos(db, apuracao.cliente_id)
    linhas = calcular_distribuicoes(
        resultado_centavos=apuracao.resultado_centavos,
        participantes=parts,
        bases_servico=bases_servico,
    )

    # limpa distribuições anteriores desta apuração (recálculo)
    for antiga in list(apuracao.distribuicoes):
        await db.delete(antiga)
    apuracao.distribuicoes.clear()

    novas: list[DistribuicaoSCP] = []
    for linha in linhas:
        dist = DistribuicaoSCP(
            apuracao_id=apuracao.id,
            participante_id=linha.participante_id,
            beneficiario_id=linha.beneficiario_id,
            base_centavos=linha.base_centavos,
            percentual_aplicado_bp=linha.percentual_aplicado_bp,
            valor_centavos=linha.valor_centavos,
        )
        db.add(dist)
        novas.append(dist)

    return novas


__all__ = [
    "LinhaDistribuicao",
    "calcular_distribuicoes",
    "fechar_resultado",
    "gerar_distribuicao",
    "participantes_ativos",
]
