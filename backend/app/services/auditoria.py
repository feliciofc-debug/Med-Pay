"""Service de auditoria — registra TODA operação financeira.

REGRA DE OURO: chamar `registrar()` sempre que algo sensível acontecer:
- Aprovação de lote
- Geração de arquivo CNAB
- Edição manual de pagamento
- Login/logout do aprovador
- Acesso a dados sensíveis (CPF/conta em claro)

NUNCA registrar CPF/conta em plaintext nos detalhes — usar versões mascaradas.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auditoria import Auditoria
from app.models.user import User


class AuditoriaService:
    """Encapsula registro de auditoria."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def registrar(
        self,
        *,
        acao: str,
        user: User | None,
        entidade_tipo: str | None = None,
        entidade_id: UUID | None = None,
        detalhes: dict[str, Any] | None = None,
        hash_relacionado: str | None = None,
        mensagem: str | None = None,
        request: Request | None = None,
    ) -> Auditoria:
        """Cria registro de auditoria.

        Args:
            acao: verbo no passado (ex: "LOTE_APROVADO", "CNAB_GERADO")
            user: usuário que executou (None só em casos sistema)
            entidade_tipo: ex: "Lote", "Pagamento", "Cliente"
            entidade_id: UUID da entidade afetada
            detalhes: dict serializável (NUNCA com CPF/conta em claro)
            hash_relacionado: hash do conteúdo afetado (ex: hash do CNAB)
            mensagem: descrição livre em português
            request: FastAPI Request (extrai ip + user-agent)
        """
        ip_address: str | None = None
        user_agent: str | None = None
        if request is not None:
            client = request.client
            ip_address = client.host if client else None
            user_agent = request.headers.get("user-agent")

        evento = Auditoria(
            user_id=user.id if user else None,
            acao=acao,
            entidade_tipo=entidade_tipo,
            entidade_id=entidade_id,
            detalhes=detalhes,
            hash_relacionado=hash_relacionado,
            ip_address=ip_address,
            user_agent=user_agent,
            mensagem=mensagem,
        )
        self.db.add(evento)
        await self.db.flush()
        return evento


__all__ = ["AuditoriaService"]
