"""Schemas das Contas de Repasse (multi-conta por tenant).

Reaproveita os campos bancários de EmpresaPagadora e acrescenta os campos
da carteira: apelido, modo_execucao e o dono (cliente_id).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.empresa_config import ModoExecucao
from app.schemas.admin import EmpresaPagadoraOut, EmpresaPagadoraRequest


class ContaRepasseRequest(EmpresaPagadoraRequest):
    """Cria/atualiza uma conta de repasse.

    `cliente_id` só é usado por admin interno pra cadastrar conta em nome de
    outro tenant; o GESTOR de um tenant cria sempre pra si (ignora o campo).
    """

    apelido: str | None = Field(default=None, max_length=80)
    modo_execucao: ModoExecucao = ModoExecucao.CNAB
    cliente_id: UUID | None = None


class ContaRepasseOut(EmpresaPagadoraOut):
    """Conta de repasse com os campos da carteira."""

    model_config = ConfigDict(from_attributes=True)

    apelido: str | None = None
    modo_execucao: ModoExecucao = ModoExecucao.CNAB
    cliente_id: UUID | None = None


__all__ = ["ContaRepasseOut", "ContaRepasseRequest"]
