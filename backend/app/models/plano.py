"""Planos comerciais da MedPag.

Define o "pacote" que cada cliente assina. Cada plano traz:

- Features padrão (CNAB sim, Sentinela não, etc) — armazenadas num
  dict JSONB pra flexibilidade total sem precisar de migration toda
  vez que aparece feature nova.
- Limites de uso (qtd pagamentos/mês, qtd usuários).
- Preço de mensalidade.
- Dias de trial (só o "Inicial" tem; os outros são contratuais).

Plano vs Cliente.features_override:
    O plano define o DEFAULT. O cliente pode ter override pontual
    (ex: cliente do "Profissional" mas com Sentinela liberado por
    cortesia). O resolver de features sempre consulta override
    primeiro, depois o plano.

Status da assinatura:
    TRIAL — em período de teste (só plano Inicial)
    ATIVO — pagando, tudo liberado
    INADIMPLENTE — pagamento atrasado, ainda acessa
    SUSPENSO — não acessa (login redireciona pra tela de regularização)
    CANCELADO — encerrou o contrato
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class StatusAssinatura(str, Enum):
    """Estado comercial da assinatura do cliente."""

    TRIAL = "TRIAL"
    ATIVO = "ATIVO"
    INADIMPLENTE = "INADIMPLENTE"
    SUSPENSO = "SUSPENSO"
    CANCELADO = "CANCELADO"


class Plano(Base):
    """Plano comercial (Inicial / Profissional / Avançado / Enterprise).

    `features` carrega o dict completo de features padrão do plano.
    Chaves seguem o padrão `categoria.nome` documentado em
    `app.services.feature_flags.FEATURES_DISPONIVEIS`.

    Exemplo de `features`:
        {
            "pagamento.cnab": True,
            "pagamento.folha_municipal": False,
            "modulo.whatsapp_jarvis": True,
            "modulo.sentinela_vital": False,
            "limite.pagamentos_mes": 1000,
            "limite.usuarios": 10
        }
    """

    __tablename__ = "planos"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    slug: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        unique=True,
        index=True,
        comment="Identificador estável (inicial, profissional, avancado, enterprise).",
    )
    nome: Mapped[str] = mapped_column(String(80), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)

    preco_mensal_centavos: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Preço em centavos pra evitar float. 0 = sob demanda (Enterprise).",
    )
    trial_dias: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Dias de trial ao assinar este plano. 0 = sem trial.",
    )

    features: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Features liberadas no plano + limites. Veja FEATURES_DISPONIVEIS.",
    )

    publico: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Se aparece na tela de signup público (false = só contratual).",
    )
    ordem: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Ordem de exibição no signup (menor = primeiro).",
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Plano slug={self.slug} preco={self.preco_mensal_centavos}>"


__all__ = ["Plano", "StatusAssinatura"]
