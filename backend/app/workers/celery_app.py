"""App Celery — broker e backend = Redis.

Inclui automaticamente todas as tasks definidas em `app.workers.tasks`.

Beat schedule:
- jarvis_relatorio_diario: roda às 8h America/Sao_Paulo, todos os dias.
  Para cada WhatsAppUser com `receber_relatorio_diario=True`, monta um
  diagnóstico e envia via WhatsApp.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "medpag",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,                  # só dá ack após task completar
    worker_prefetch_multiplier=1,         # não pega mais que está executando
    task_reject_on_worker_lost=True,      # devolve task pra fila se worker morrer
    result_expires=60 * 60 * 24,          # resultado guardado por 24h
    beat_schedule={
        "jarvis-relatorio-diario": {
            "task": "app.workers.tasks.jarvis_relatorio_diario",
            # 8h de Sao Paulo, todos os dias
            "schedule": crontab(hour=8, minute=0),
        },
    },
)


__all__ = ["celery_app"]
