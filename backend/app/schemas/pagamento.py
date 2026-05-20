"""Schemas de Pagamento."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AceitarSugestaoCPFRequest(BaseModel):
    """Operador aceita a sugestão de CPF que o sistema fez."""

    aceitar: bool = True


class EditarPagamentoRequest(BaseModel):
    """Edição manual de campos do pagamento (durante revisão)."""

    cpf: str | None = Field(None, max_length=14)
    nome: str | None = Field(None, max_length=255)
    banco_codigo: str | None = Field(None, max_length=3)
    agencia: str | None = Field(None, max_length=10)
    conta: str | None = Field(None, max_length=20)
    valor_centavos: int | None = Field(None, gt=0)
