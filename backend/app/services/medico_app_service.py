"""Service do app do medico (prestador).

Responde 3 perguntas que o medico tem ao entrar:
- "Quem sou eu na plataforma?" (perfil + vinculo)
- "Quais plantoes eu ja fiz?" (servicos lançados em fichas)
- "Quanto eu ja recebi e o que esta pra receber?" (extrato de pagamentos)

Regra de seguranca:
    Todos os endpoints trabalham SO com `current_user.beneficiario_id`.
    Se for None, devolve aviso "medico nao vinculado" e zera os dados
    em vez de vazar info de outro prestador.

Multi-tenant ja vem garantido: o User MEDICO tem cliente_id setado, e
o Beneficiario tambem. Confiamos no get_current_user pra carregar isso.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.beneficiario import Beneficiario
from app.models.ficha_plantao import FichaPlantao, StatusFicha
from app.models.lote import Lote
from app.models.pagamento import Pagamento, StatusPagamento
from app.models.user import User
from app.validators.cpf import limpar_cpf


# ============================================================
# Dataclasses de saida
# ============================================================


@dataclass(slots=True)
class PerfilMedico:
    nome: str
    email: str
    cpf_mascarado: str | None
    hospital: str | None
    hospital_id: str | None
    beneficiario_id: str | None
    vinculado: bool
    pix_modalidade: str | None       # "PIX" / "TED" / None
    pix_chave_mascarada: str | None
    banco_nome: str | None
    conta_mascarada: str | None
    conta_verificada: bool


@dataclass(slots=True)
class PlantaoItem:
    ficha_id: str
    nome_arquivo: str
    competencia: str | None
    coordenador: str | None
    data_lancamento: datetime
    status_ficha: str
    valor_centavos: int
    detalhe: str | None


@dataclass(slots=True)
class PagamentoItem:
    pagamento_id: str
    lote_id: str
    valor_centavos: int
    status: str
    status_label: str
    modalidade: str
    criado_em: datetime
    pago_em: datetime | None
    motivo_rejeicao: str | None


@dataclass(slots=True)
class ResumoExtrato:
    total_pago_centavos: int
    total_pendente_centavos: int
    total_rejeitado_centavos: int
    qtd_pagamentos: int


# ============================================================
# Helpers
# ============================================================


_STATUS_LABEL = {
    StatusPagamento.VALIDO: "Validado",
    StatusPagamento.CORRIGIVEL: "Aguardando correção",
    StatusPagamento.BLOQUEADO: "Bloqueado",
    StatusPagamento.APROVADO: "Aprovado para pagamento",
    StatusPagamento.REJEITADO: "Rejeitado",
    StatusPagamento.PAGO: "Pago",
    StatusPagamento.NAO_PAGO: "Não pago (banco rejeitou)",
}


# ============================================================
# /me
# ============================================================


async def obter_perfil(db: AsyncSession, user: User) -> PerfilMedico:
    """Retorna o perfil do medico logado."""
    if user.beneficiario_id is None:
        # Nao vinculado: devolve so o basico do User
        return PerfilMedico(
            nome=user.nome,
            email=user.email,
            cpf_mascarado=None,
            hospital=user.cliente.nome if user.cliente else None,
            hospital_id=str(user.cliente_id) if user.cliente_id else None,
            beneficiario_id=None,
            vinculado=False,
            pix_modalidade=None,
            pix_chave_mascarada=None,
            banco_nome=None,
            conta_mascarada=None,
            conta_verificada=False,
        )

    q = select(Beneficiario).where(Beneficiario.id == user.beneficiario_id)
    result = await db.execute(q)
    b = result.scalar_one_or_none()
    if b is None:
        # Vinculo orfao (Beneficiario deletado) — trata como nao vinculado
        return PerfilMedico(
            nome=user.nome,
            email=user.email,
            cpf_mascarado=None,
            hospital=user.cliente.nome if user.cliente else None,
            hospital_id=str(user.cliente_id) if user.cliente_id else None,
            beneficiario_id=None,
            vinculado=False,
            pix_modalidade=None,
            pix_chave_mascarada=None,
            banco_nome=None,
            conta_mascarada=None,
            conta_verificada=False,
        )

    modalidade = None
    chave = None
    if b.pix_chave_mascarada:
        modalidade = "PIX"
        chave = b.pix_chave_mascarada
    elif b.banco_codigo and b.conta_mascarada:
        modalidade = "TED"

    banco_nome = None
    if b.banco_codigo:
        from app.validators.banco import nome_banco

        banco_nome = nome_banco(b.banco_codigo)

    return PerfilMedico(
        nome=user.nome,
        email=user.email,
        cpf_mascarado=b.cpf_mascarado,
        hospital=user.cliente.nome if user.cliente else None,
        hospital_id=str(user.cliente_id) if user.cliente_id else None,
        beneficiario_id=str(b.id),
        vinculado=True,
        pix_modalidade=modalidade,
        pix_chave_mascarada=chave,
        banco_nome=banco_nome,
        conta_mascarada=b.conta_mascarada,
        conta_verificada=b.conta_verificada,
    )


# ============================================================
# /plantoes
# ============================================================


def _linhas_da_ficha(ficha: FichaPlantao) -> list[dict]:
    """Devolve as linhas extraidas da ficha (lista de dicts)."""
    linhas = ficha.linhas_extraidas or []
    if not isinstance(linhas, list):
        return []
    return [linha for linha in linhas if isinstance(linha, dict)]


async def listar_plantoes(
    db: AsyncSession,
    user: User,
    *,
    limit: int = 50,
) -> list[PlantaoItem]:
    """Lista plantoes (fichas) onde o CPF do medico aparece.

    Estrategia:
    1. Carrega o CPF do beneficiario (limpo, 11 digitos)
    2. Faz query em FichaPlantao do mesmo cliente_id
    3. Filtra na app os que tem o CPF nas linhas extraidas

    Nao usamos cpf_hash aqui porque as fichas guardam o CPF como
    texto cru no JSON `dados_extraidos`, nao um hash indexado.
    """
    if user.beneficiario_id is None or user.cliente_id is None:
        return []

    # Pega CPF cru do beneficiario (precisa decifrar)
    q_b = select(Beneficiario).where(Beneficiario.id == user.beneficiario_id)
    b = (await db.execute(q_b)).scalar_one_or_none()
    if b is None:
        return []

    from app.core.crypto import decrypt

    try:
        cpf_cru = decrypt(b.cpf_encrypted)
    except Exception:
        return []
    cpf_limpo = limpar_cpf(cpf_cru)
    if not cpf_limpo:
        return []

    q_f = (
        select(FichaPlantao)
        .where(
            FichaPlantao.cliente_id == user.cliente_id,
            FichaPlantao.status.in_(
                [
                    StatusFicha.EXTRAIDA,
                    StatusFicha.REVISADA,
                    StatusFicha.CONVERTIDA,
                ]
            ),
        )
        .order_by(FichaPlantao.created_at.desc())
        .limit(limit * 5)  # busca mais e filtra na app
    )
    fichas = list((await db.execute(q_f)).scalars())

    plantoes: list[PlantaoItem] = []
    for ficha in fichas:
        for linha in _linhas_da_ficha(ficha):
            if not isinstance(linha, dict):
                continue
            cpf_linha = limpar_cpf(str(linha.get("cpf") or ""))
            if cpf_linha != cpf_limpo:
                continue
            valor_str = linha.get("valor_centavos") or linha.get("valor") or 0
            try:
                valor_centavos = int(valor_str)
            except (TypeError, ValueError):
                valor_centavos = 0
            detalhe = str(
                linha.get("descricao")
                or linha.get("servico")
                or linha.get("especialidade")
                or ""
            ) or None

            meta = ficha.metadados or {}
            plantoes.append(
                PlantaoItem(
                    ficha_id=str(ficha.id),
                    nome_arquivo=ficha.nome_arquivo or "ficha",
                    competencia=meta.get("competencia"),
                    coordenador=meta.get("coordenador"),
                    data_lancamento=ficha.created_at,
                    status_ficha=ficha.status.value,
                    valor_centavos=valor_centavos,
                    detalhe=detalhe,
                )
            )

    # Ordena pelo mais recente e respeita limit
    plantoes.sort(key=lambda p: p.data_lancamento, reverse=True)
    return plantoes[:limit]


# ============================================================
# /extrato
# ============================================================


async def listar_pagamentos(
    db: AsyncSession,
    user: User,
    *,
    limit: int = 100,
) -> tuple[list[PagamentoItem], ResumoExtrato]:
    """Lista pagamentos amarrados ao beneficiario do medico + resumo."""
    if user.beneficiario_id is None:
        return [], ResumoExtrato(0, 0, 0, 0)

    q = (
        select(Pagamento)
        .where(Pagamento.beneficiario_id == user.beneficiario_id)
        .options(selectinload(Pagamento.lote).selectinload(Lote.cliente))
        .order_by(Pagamento.created_at.desc())
        .limit(limit)
    )
    pagamentos = list((await db.execute(q)).scalars())

    items: list[PagamentoItem] = []
    total_pago = 0
    total_pendente = 0
    total_rejeitado = 0
    for p in pagamentos:
        items.append(
            PagamentoItem(
                pagamento_id=str(p.id),
                lote_id=str(p.lote_id),
                valor_centavos=p.valor_centavos,
                status=p.status.value,
                status_label=_STATUS_LABEL.get(p.status, p.status.value),
                modalidade=p.modalidade.value if p.modalidade else "—",
                criado_em=p.created_at,
                pago_em=p.pago_at,
                motivo_rejeicao=p.retorno_descricao if p.status in (
                    StatusPagamento.NAO_PAGO,
                    StatusPagamento.REJEITADO,
                ) else None,
            )
        )
        if p.status == StatusPagamento.PAGO:
            total_pago += p.valor_centavos
        elif p.status in (StatusPagamento.NAO_PAGO, StatusPagamento.REJEITADO):
            total_rejeitado += p.valor_centavos
        else:
            total_pendente += p.valor_centavos

    resumo = ResumoExtrato(
        total_pago_centavos=total_pago,
        total_pendente_centavos=total_pendente,
        total_rejeitado_centavos=total_rejeitado,
        qtd_pagamentos=len(items),
    )
    return items, resumo
