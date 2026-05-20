"""Tasks Celery — execução em background.

Como Celery não suporta async nativamente (sem celery 5.4+ com asyncio
ainda em beta), envolvemos a lógica async em `asyncio.run()`.

REGRAS:
- Tasks são idempotentes (aceita reexecução sem efeito colateral)
- Task curta (segundos) ok síncronas; longas (minutos) considerar progresso
- NUNCA logar dado sensível
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.lote import Lote, StatusLote
from app.services.importacao import LinhaPlanilha
from app.services.processamento import processar_lote
from app.workers.celery_app import celery_app

log = structlog.get_logger()


async def _processar_lote_async(
    lote_id: UUID, linhas_dict: list[dict[str, str | None]]
) -> dict[str, int]:
    """Carrega o Lote, reconstrói as linhas e roda o processamento."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Lote).where(Lote.id == lote_id))
        lote = result.scalar_one_or_none()
        if lote is None:
            log.error("worker.lote_nao_encontrado", lote_id=str(lote_id))
            return {"total": 0, "validos": 0, "corrigiveis": 0, "bloqueados": 0}

        if lote.status not in (StatusLote.RECEBIDO, StatusLote.ERRO):
            log.warning(
                "worker.lote_status_invalido",
                lote_id=str(lote_id),
                status=lote.status.value,
            )
            return {
                "total": lote.total_pagamentos,
                "validos": lote.total_validos,
                "corrigiveis": lote.total_corrigiveis,
                "bloqueados": lote.total_bloqueados,
            }

        linhas = [
            LinhaPlanilha(
                numero_linha=int(d["numero_linha"]),  # type: ignore[arg-type]
                cpf_raw=d.get("cpf_raw"),
                nome_raw=d.get("nome_raw"),
                banco_raw=d.get("banco_raw"),
                agencia_raw=d.get("agencia_raw"),
                conta_raw=d.get("conta_raw"),
                valor_raw=d.get("valor_raw"),
            )
            for d in linhas_dict
        ]

        try:
            resultado = await processar_lote(db, lote, linhas)
            await db.commit()
            log.info(
                "worker.lote_processado",
                lote_id=str(lote_id),
                total=resultado.total,
                validos=resultado.validos,
                corrigiveis=resultado.corrigiveis,
                bloqueados=resultado.bloqueados,
            )
            return {
                "total": resultado.total,
                "validos": resultado.validos,
                "corrigiveis": resultado.corrigiveis,
                "bloqueados": resultado.bloqueados,
            }
        except Exception as exc:
            log.exception("worker.lote_erro", lote_id=str(lote_id), erro=str(exc))
            lote.status = StatusLote.ERRO
            lote.mensagem_erro = f"Erro no processamento: {exc}"
            await db.commit()
            raise


@celery_app.task(name="medpag.processar_lote", bind=True, max_retries=3)
def processar_lote_task(
    self, lote_id_str: str, linhas_dict: list[dict[str, str | None]]
) -> dict[str, int]:
    """Task Celery que processa um lote em background.

    Args:
        lote_id_str: UUID do lote em string (Celery serializa em JSON)
        linhas_dict: lista de dicts representando LinhaPlanilha

    Returns:
        Dict com totais (validos, corrigiveis, bloqueados)
    """
    lote_id = UUID(lote_id_str)
    return asyncio.run(_processar_lote_async(lote_id, linhas_dict))


__all__ = ["processar_lote_task"]
