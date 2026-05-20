"""Schemas comuns reutilizados em várias respostas."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    """Resposta padrão de sucesso."""

    success: bool = True
    data: T


class ErrorDetail(BaseModel):
    """Detalhe de um erro de validação por campo."""

    field: str
    line: int | None = None
    code: str
    message: str
    suggestion: str | None = None


class ErrorResponse(BaseModel):
    """Resposta padrão de erro de validação ou negócio."""

    success: bool = False
    error: dict[str, str] | None = None
    errors: list[ErrorDetail] | None = None


class PaginatedMeta(BaseModel):
    """Metadados de paginação."""

    page: int = Field(ge=1, description="Página atual (1-indexed)")
    page_size: int = Field(ge=1, le=200)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class Paginated(BaseModel, Generic[T]):
    """Resposta paginada genérica."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[T]
    meta: PaginatedMeta
