"""Modelo de Cliente (hospital, clínica, ONG que envia planilhas)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.plano import Plano, StatusAssinatura

if TYPE_CHECKING:
    from app.models.lote import Lote


class TipoCliente(str, Enum):
    """QUEM é o tenant (Eixo 1 da engenharia de modelos de negócio).

    Define a "natureza" do cliente — não confunda com features (Eixo 2,
    o QUE pode fazer) nem com modo de pagamento (Eixo 3, COMO o dinheiro
    sai). Cada tipo é só um preset de defaults; ajuste fino vai no
    `features_override`.

    HOSPITAL         — hospital/clínica que paga os próprios médicos.
                       Dashboard de gestão (sem lucro), foco presença.
    EMPRESA_REPASSE  — empresa de repasse que CONTRATA a MedPag e atende
                       vários hospitais (tenant "pai" com filhos).
    MEDPAG_REPASSE   — a própria MedPag operando o repasse (modelo SCP,
                       médicos como sócios participantes).
    ONG              — organização do terceiro setor, perfil enxuto.
    """

    HOSPITAL = "HOSPITAL"
    EMPRESA_REPASSE = "EMPRESA_REPASSE"
    MEDPAG_REPASSE = "MEDPAG_REPASSE"
    ONG = "ONG"


class ModoPagamento(str, Enum):
    """COMO o repasse ao médico é executado (Eixo 3).

    IMPORTANTE: o dinheiro do repasse NUNCA passa pela MedPag — sai da
    conta do hospital (ou da SCP), sempre em banco tradicional. A MedPag
    orquestra/gera o arquivo, não custodia. O Asaas só recebe a
    mensalidade SaaS e valida CPF/PIX — nunca faz repasse.

    CNAB_BANCARIO  — gera CNAB 240; o hospital deposita pelo banco dele.
    EXPORT_RH      — exporta arquivo/planilha pro RH do cliente processar
                     (hospital público, folha municipal/eSocial).
    REPASSE_SCP    — MedPag opera como sócio ostensivo (SCP): apura
                     resultado e distribui aos médicos participantes,
                     ainda via banco tradicional.
    SOMENTE_GESTAO — não executa pagamento; só gestão/relatórios.
    """

    CNAB_BANCARIO = "CNAB_BANCARIO"
    EXPORT_RH = "EXPORT_RH"
    REPASSE_SCP = "REPASSE_SCP"
    SOMENTE_GESTAO = "SOMENTE_GESTAO"


class Cliente(Base):
    """Cliente que envia planilhas de pagamento.

    Tipicamente um hospital, clínica ou ONG. Cada cliente pode ter
    formato próprio de planilha — o mapeamento de colunas é salvo
    em `mapeamento_colunas` (JSON) pra reaproveitar.
    """

    __tablename__ = "clientes"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    nome: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True, unique=True, index=True)
    email_contato: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Email autorizado a enviar planilhas (whitelist)
    # Quando email chega de um remetente nesta lista, sistema identifica o cliente
    email_remetente_autorizado: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    # Mapeamento de colunas da planilha deste cliente
    # Ex: {"cpf": "Documento", "nome": "Beneficiário", "valor": "Valor Bruto", ...}
    mapeamento_colunas: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # ---------- Eixo 1: Tipo de tenant (modelo de negócio) ----------
    # Define a natureza do cliente. Só um preset de defaults — o que ele
    # PODE fazer continua nas features (Eixo 2). Default HOSPITAL pra
    # clientes legados nascerem como hospital sem migração de dados.
    tipo: Mapped[TipoCliente] = mapped_column(
        SAEnum(
            TipoCliente,
            name="tipo_cliente",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,  # type criado via migration idempotente
        ),
        nullable=False,
        default=TipoCliente.HOSPITAL,
        server_default=TipoCliente.HOSPITAL.value,
        index=True,
    )

    # ---------- Eixo 3: Modo de execução do repasse ----------
    # COMO o pagamento ao médico sai. Default CNAB_BANCARIO (o que já
    # existe hoje). Ver `ModoPagamento` — o dinheiro nunca passa pela
    # MedPag; Asaas é só mensalidade + validação de CPF.
    modo_pagamento: Mapped[ModoPagamento] = mapped_column(
        SAEnum(
            ModoPagamento,
            name="modo_pagamento_cliente",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=False,
        default=ModoPagamento.CNAB_BANCARIO,
        server_default=ModoPagamento.CNAB_BANCARIO.value,
    )

    # ---------- Hierarquia (empresa de repasse → hospitais filhos) ----------
    # Quando setado, este cliente é "filho" de um tenant pai (ex.: uma
    # empresa de repasse que administra vários hospitais). Null = raiz.
    # A visão consolidada do pai soma os filhos.
    cliente_pai_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ---------- Plano + Assinatura ----------
    # Cada cliente assina um plano que define features padrão e limites.
    # Nullable porque clientes legados nascem sem plano e migram depois.
    plano_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("planos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Overrides pontuais do plano (ex: cliente Profissional com Sentinela
    # liberado por cortesia). Dict no mesmo formato do Plano.features.
    # Vazio = usa tudo do plano. Resolver checa override antes do plano.
    features_override: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Overrides do cliente sobre o plano. Vazio = usa só o plano.",
    )

    status_assinatura: Mapped[StatusAssinatura] = mapped_column(
        SAEnum(
            StatusAssinatura,
            name="status_assinatura",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=StatusAssinatura.ATIVO,
        server_default=StatusAssinatura.ATIVO.value,
        index=True,
    )

    # Setado quando cliente nasce em TRIAL. Null fora desse estado.
    trial_termina_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # ---------- Asaas (cobrança recorrente) ----------
    # ID do customer dentro do Asaas. Setado quando o signup cria o
    # registro de cobrança. Null quando cliente é manual/legado.
    asaas_customer_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )
    # ID da assinatura ativa no Asaas (subscription).
    asaas_subscription_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True
    )
    # Próximo vencimento conhecido (sync com webhooks do Asaas).
    proximo_vencimento: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # Se o cliente já cadastrou meio de pagamento no Asaas (pra signup
    # decidir se cobra direto ou só inicia trial).
    pagamento_cadastrado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # ---------- Configuração operacional (per-tenant) ----------
    # Dia do mês em que o fechamento de pagamentos ocorre (1-31, ou 0
    # pra "último dia útil"). Cliente edita pela tela Configurar Operação.
    dia_fechamento: Mapped[int] = mapped_column(
        Integer, nullable=False, default=25, server_default="25"
    )
    # Fuso IANA (ex: "America/Sao_Paulo"). Default Brasília.
    fuso_horario: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="America/Sao_Paulo",
        server_default="America/Sao_Paulo",
    )
    # Modalidade preferencial pra novos lançamentos (PIX/TED/CC).
    # Soft hint — não bloqueia outras escolhas.
    modalidade_preferida: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PIX",
        server_default="PIX",
    )
    # Logo do cliente (URL pública). Usado em comprovantes PDF + UI.
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Cor primária pra branding (hex sem #). Default brand-600.
    cor_primaria: Mapped[str] = mapped_column(
        String(7), nullable=False, default="#2D5F3F", server_default="#2D5F3F"
    )

    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relacionamentos
    lotes: Mapped[list["Lote"]] = relationship("Lote", back_populates="cliente")
    plano: Mapped["Plano | None"] = relationship("Plano", lazy="joined")

    # Hierarquia: empresa de repasse (pai) ↔ hospitais administrados (filhos).
    cliente_pai: Mapped["Cliente | None"] = relationship(
        "Cliente",
        remote_side=[id],
        back_populates="filhos",
        foreign_keys=[cliente_pai_id],
    )
    filhos: Mapped[list["Cliente"]] = relationship(
        "Cliente",
        back_populates="cliente_pai",
        foreign_keys=[cliente_pai_id],
    )

    def __repr__(self) -> str:
        return f"<Cliente id={self.id} nome={self.nome} tipo={self.tipo}>"


__all__ = ["Cliente", "ModoPagamento", "TipoCliente"]
