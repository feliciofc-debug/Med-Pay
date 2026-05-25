"""Ficha de plantão escaneada/fotografada (origem do banco de horas).

Substitui o fluxo manual da escalista preparando planilha. O coordenador
do hospital sobe a foto/PDF da ficha carimbada, o OCR extrai os dados
e o aprovador revisa antes de virar lote.

Fluxo:
    RECEBIDA  →  PROCESSANDO  →  EXTRAIDA  →  REVISADA  →  CONVERTIDA
                                       \\
                                        →  ERRO

- RECEBIDA:    upload feito, ainda não foi pro OCR
- PROCESSANDO: OCR em andamento (worker / on-demand)
- EXTRAIDA:    texto extraído com sucesso, dados parseados (mesmo que parciais)
- REVISADA:    coordenador/admin conferiu e ajustou os campos
- CONVERTIDA:  virou linhas em um lote de pagamento
- ERRO:        OCR ou parser falharam — `mensagem_erro` tem o motivo
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cliente import Cliente
    from app.models.lote import Lote
    from app.models.user import User


class StatusFicha(str, Enum):
    """Estados pelos quais uma ficha passa."""

    RECEBIDA = "RECEBIDA"
    PROCESSANDO = "PROCESSANDO"
    EXTRAIDA = "EXTRAIDA"
    REVISADA = "REVISADA"
    CONVERTIDA = "CONVERTIDA"
    ERRO = "ERRO"


class FichaPlantao(Base):
    """Ficha de plantão (foto/PDF carimbado) que vira lote depois de revisada.

    Os bytes do arquivo original ficam em `arquivo_bytes` para que o disco
    efêmero do Render não derrube o histórico. O texto bruto extraído pelo
    OCR fica em `texto_ocr` (auditoria) e os campos estruturados ficam
    em `linhas_extraidas` (JSON) — cada item já no formato consumível pelo
    importador de lote (cpf, nome, valor_centavos, banco, agência, conta).
    """

    __tablename__ = "fichas_plantao"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # ===== Cliente / hospital de origem =====
    cliente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False, index=True
    )

    # ===== Arquivo original =====
    nome_arquivo: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    tamanho_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    arquivo_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    hash_arquivo: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    # ===== Status =====
    status: Mapped[StatusFicha] = mapped_column(
        SAEnum(StatusFicha, name="status_ficha"),
        nullable=False,
        default=StatusFicha.RECEBIDA,
        index=True,
    )

    # ===== Resultado OCR =====
    texto_ocr: Mapped[str | None] = mapped_column(Text, nullable=True)
    paginas_ocr: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Campos estruturados parseados a partir do OCR.
    # Estrutura (lista de objetos):
    # [
    #   {
    #     "cpf": "12345678909",
    #     "nome": "Dr. Fulano",
    #     "valor_centavos": 35000,
    #     "qtd_plantoes": 4,
    #     "horas": 48,
    #     "banco_codigo": "136",
    #     "agencia": "0001",
    #     "conta": "12345-6",
    #     "chave_pix": null,
    #     "linha_origem": "Texto bruto da linha"
    #   },
    #   ...
    # ]
    linhas_extraidas: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True
    )

    # Metadados que o parser conseguiu inferir do cabeçalho da ficha.
    # Ex: {"hospital": "...", "competencia": "06/2026", "coordenador": "..."}
    metadados: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # ===== Erros =====
    mensagem_erro: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ===== Quem subiu / revisou =====
    enviado_por_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    revisado_por_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    revisado_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ===== Lote gerado (preenchido após conversão) =====
    lote_gerado_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lotes.id"), nullable=True, index=True
    )

    # ===== Timestamps =====
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ===== Relacionamentos =====
    cliente: Mapped["Cliente"] = relationship("Cliente")
    enviado_por: Mapped["User | None"] = relationship(
        "User", foreign_keys=[enviado_por_id]
    )
    revisado_por: Mapped["User | None"] = relationship(
        "User", foreign_keys=[revisado_por_id]
    )
    lote_gerado: Mapped["Lote | None"] = relationship("Lote", foreign_keys=[lote_gerado_id])

    @property
    def total_linhas(self) -> int:
        return len(self.linhas_extraidas or [])

    @property
    def valor_total_centavos(self) -> int:
        return sum(
            int(linha.get("valor_centavos") or 0)
            for linha in (self.linhas_extraidas or [])
        )

    def __repr__(self) -> str:
        return (
            f"<FichaPlantao id={self.id} arquivo={self.nome_arquivo} "
            f"status={self.status.value} linhas={self.total_linhas}>"
        )


__all__ = ["FichaPlantao", "StatusFicha"]
