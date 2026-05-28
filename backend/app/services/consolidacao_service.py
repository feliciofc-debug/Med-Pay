"""Consolidação de fichas de plantão em um extrato de pagamento.

Resolve o ponto onde o fluxo OCR estava quebrando: hoje cada ficha
vira um lote separado, então um hospital que sobe 4 fichas no mês
gera 4 lotes diferentes, cada um com poucos médicos. O coordenador
queria uma visão única: "todas as fichas pendentes do Hospital X em
06/2026 → 1 extrato consolidado → 1 lote pra pagar".

Este service oferece 3 visões de consolidação:
    1. Por hospital + competência (cliente_id + mês/ano da ficha)
    2. Por dia (cliente_id + data)
    3. Por médico (beneficiario_id ou CPF normalizado)

E uma operação:
    gerar_lote_consolidado(fichas_ids)  →  cria 1 Lote único com
        todas as linhas das N fichas, dispara processar_lote,
        marca cada ficha como CONVERTIDA apontando pro mesmo lote.

REGRAS:
    - Só fichas em EXTRAIDA ou REVISADA podem entrar (não CONVERTIDA)
    - Todas precisam ser do mesmo `cliente_id` (sanidade)
    - Linhas inválidas (sem cpf+nome+valor) são descartadas com aviso
"""

from __future__ import annotations

import hashlib
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.crypto import hash_for_lookup
from app.core.exceptions import MedPagException, ValidacaoError
from app.models.beneficiario import Beneficiario
from app.models.ficha_plantao import FichaPlantao, StatusFicha
from app.models.lote import Lote
from app.models.user import User
from app.validators.cpf import limpar_cpf

log = structlog.get_logger()


class FichasIncompativeisError(MedPagException):
    code = "FICHAS_INCOMPATIVEIS"
    status_code = 400


# ============================================================
# Dataclasses de saída (vão pros schemas Pydantic depois)
# ============================================================


@dataclass(slots=True)
class FichaResumo:
    """Resumo de 1 ficha pra mostrar no extrato consolidado."""

    id: UUID
    nome_arquivo: str
    status: str
    qtd_linhas: int
    valor_total_centavos: int
    competencia: str | None
    hospital: str | None
    coordenador: str | None
    created_at: datetime


@dataclass(slots=True)
class MedicoNoExtrato:
    """Linha consolidada por médico dentro de um extrato."""

    cpf_mascarado: str
    nome: str
    qtd_aparicoes: int          # em quantas linhas/fichas ele aparece
    valor_total_centavos: int
    beneficiario_id: UUID | None  # null = médico não cadastrado ainda
    beneficiario_cadastrado: bool


@dataclass(slots=True)
class ExtratoConsolidado:
    """Resposta de uma view de consolidação."""

    titulo: str                          # "Hospital São Lucas · 06/2026"
    cliente_id: UUID
    cliente_nome: str
    chave_agrupamento: str               # "hospital-mes" | "dia" | "medico"
    fichas: list[FichaResumo]
    medicos: list[MedicoNoExtrato]
    total_fichas: int
    total_linhas: int
    total_medicos_unicos: int
    valor_total_centavos: int
    medicos_nao_cadastrados: int         # quantos não casaram com Beneficiario


# ============================================================
# Helpers de extração das linhas brutas
# ============================================================


def _eh_linha_valida(linha: dict[str, Any]) -> bool:
    return bool(
        linha.get("cpf") and linha.get("nome") and linha.get("valor_centavos")
    )


def _cpf_hash(linha: dict[str, Any]) -> str | None:
    cpf = limpar_cpf(linha.get("cpf") or "")
    if not cpf:
        return None
    return hash_for_lookup(cpf)


def _competencia_da_ficha(ficha: FichaPlantao) -> str | None:
    """Extrai 'MM/YYYY' do campo metadados.competencia, normalizado."""
    meta = ficha.metadados or {}
    comp = meta.get("competencia")
    if not comp:
        return None
    # Aceita "06/2026", "06-2026", "06.2026", "junho/2026"
    s = str(comp).strip()
    m = re.search(r"(\d{1,2})[\/\-\.\s](\d{4})", s)
    if m:
        return f"{int(m.group(1)):02d}/{m.group(2)}"
    return s


def _competencia_de_data(d: datetime) -> str:
    return d.strftime("%m/%Y")


# ============================================================
# View 1: Por Hospital + Competência
# ============================================================


async def consolidar_por_hospital_mes(
    db: AsyncSession,
    *,
    cliente_id: UUID,
    competencia: str | None = None,
) -> ExtratoConsolidado:
    """Consolida fichas pendentes (EXTRAIDA + REVISADA) de um cliente
    em uma competência (MM/YYYY). Se competencia=None, pega o mês atual.
    """
    competencia_alvo = competencia or _competencia_de_data(datetime.utcnow())

    fichas = await _carregar_fichas_pendentes(db, cliente_id=cliente_id)
    fichas_da_competencia = [
        f for f in fichas if _competencia_da_ficha(f) == competencia_alvo
    ]
    cliente_nome = _nome_cliente(fichas_da_competencia, fichas)

    return await _montar_extrato(
        db,
        cliente_id=cliente_id,
        cliente_nome=cliente_nome,
        titulo=f"{cliente_nome} · {competencia_alvo}",
        chave="hospital-mes",
        fichas=fichas_da_competencia,
    )


# ============================================================
# View 2: Por dia
# ============================================================


async def consolidar_por_dia(
    db: AsyncSession,
    *,
    cliente_id: UUID,
    data: datetime,
) -> ExtratoConsolidado:
    """Fichas subidas no MESMO dia (created_at) — estilo bolo do dia."""
    inicio = data.replace(hour=0, minute=0, second=0, microsecond=0)
    fim = inicio + timedelta(days=1)

    fichas_q = await db.execute(
        select(FichaPlantao)
        .where(
            FichaPlantao.cliente_id == cliente_id,
            FichaPlantao.status.in_(
                [StatusFicha.EXTRAIDA, StatusFicha.REVISADA]
            ),
            FichaPlantao.created_at >= inicio,
            FichaPlantao.created_at < fim,
        )
        .options(selectinload(FichaPlantao.cliente))
        .order_by(FichaPlantao.created_at)
    )
    fichas = list(fichas_q.scalars())
    cliente_nome = _nome_cliente(fichas, fichas)

    return await _montar_extrato(
        db,
        cliente_id=cliente_id,
        cliente_nome=cliente_nome,
        titulo=f"{cliente_nome} · {data.strftime('%d/%m/%Y')}",
        chave="dia",
        fichas=fichas,
    )


# ============================================================
# View 3: Por médico (todas as fichas onde ele aparece)
# ============================================================


async def consolidar_por_medico(
    db: AsyncSession,
    *,
    cliente_id: UUID,
    beneficiario_id: UUID | None = None,
    cpf: str | None = None,
) -> ExtratoConsolidado:
    """Mostra todas as fichas PENDENTES (EXTRAIDA/REVISADA) do cliente
    em que o médico (identificado por beneficiario_id OU CPF) aparece.

    Útil pra responder: "quanto o Dr. X tem a receber em fichas abertas?"
    """
    cpf_hash_alvo: str | None = None
    if beneficiario_id:
        ben_q = await db.execute(
            select(Beneficiario.cpf_hash).where(Beneficiario.id == beneficiario_id)
        )
        cpf_hash_alvo = ben_q.scalar_one_or_none()
        if cpf_hash_alvo is None:
            raise ValidacaoError("Beneficiário não encontrado.")
    elif cpf:
        cpf_limpo = limpar_cpf(cpf)
        if not cpf_limpo:
            raise ValidacaoError("CPF inválido.")
        cpf_hash_alvo = hash_for_lookup(cpf_limpo)
    else:
        raise ValidacaoError("Informe beneficiario_id ou cpf.")

    todas = await _carregar_fichas_pendentes(db, cliente_id=cliente_id)

    # Filtra fichas que TENHAM esse médico em alguma linha
    relevantes: list[FichaPlantao] = []
    for f in todas:
        linhas = f.linhas_extraidas or []
        for linha in linhas:
            if _cpf_hash(linha) == cpf_hash_alvo:
                relevantes.append(f)
                break

    cliente_nome = _nome_cliente(relevantes, todas)
    nome_medico = "Médico"
    for f in relevantes:
        for linha in f.linhas_extraidas or []:
            if _cpf_hash(linha) == cpf_hash_alvo and linha.get("nome"):
                nome_medico = str(linha["nome"]).strip()
                break
        if nome_medico != "Médico":
            break

    return await _montar_extrato(
        db,
        cliente_id=cliente_id,
        cliente_nome=cliente_nome,
        titulo=f"{nome_medico} · {cliente_nome}",
        chave="medico",
        fichas=relevantes,
        filtro_cpf_hash=cpf_hash_alvo,
    )


# ============================================================
# Operação: gerar lote consolidado (N fichas → 1 lote)
# ============================================================


async def gerar_lote_consolidado(
    db: AsyncSession,
    *,
    fichas_ids: list[UUID],
    usuario: User,
    referencia: str | None = None,
) -> Lote:
    """Une N fichas num único lote, dispara processar_lote.

    - Todas as fichas precisam ser do mesmo cliente
    - Todas precisam estar em EXTRAIDA ou REVISADA
    - Linhas inválidas são silenciosamente descartadas
    - Cada ficha vira CONVERTIDA apontando pro mesmo lote_id
    """
    if not fichas_ids:
        raise ValidacaoError("Selecione pelo menos uma ficha.")

    fichas_q = await db.execute(
        select(FichaPlantao)
        .where(FichaPlantao.id.in_(fichas_ids))
        .options(selectinload(FichaPlantao.cliente))
    )
    fichas = list(fichas_q.scalars())

    if len(fichas) != len(fichas_ids):
        raise ValidacaoError("Uma ou mais fichas não foram encontradas.")

    clientes = {f.cliente_id for f in fichas}
    if len(clientes) > 1:
        raise FichasIncompativeisError(
            "Fichas de hospitais diferentes não podem virar um lote único. "
            "Gere um lote por cliente."
        )

    statuses_ok = {StatusFicha.EXTRAIDA, StatusFicha.REVISADA}
    fichas_invalidas = [
        f.id for f in fichas if f.status not in statuses_ok
    ]
    if fichas_invalidas:
        raise ValidacaoError(
            f"Fichas em status inválido pra consolidação: "
            f"{[str(i) for i in fichas_invalidas]}. "
            "Só EXTRAIDA ou REVISADA podem ser consolidadas."
        )

    cliente = fichas[0].cliente

    # Une as linhas válidas (preservando origem)
    linhas_consolidadas: list[dict[str, Any]] = []
    for ficha in fichas:
        for linha in ficha.linhas_extraidas or []:
            if _eh_linha_valida(linha):
                linha_copia = dict(linha)
                linha_copia["_ficha_origem"] = str(ficha.id)
                linhas_consolidadas.append(linha_copia)

    if not linhas_consolidadas:
        raise ValidacaoError(
            "Nenhuma ficha tem linhas válidas (CPF+nome+valor). "
            "Revise as fichas antes de consolidar."
        )

    xlsx_bytes = _linhas_para_xlsx(linhas_consolidadas)
    # Sufixo único pra evitar hash colisão com outras consolidações
    hash_sufixo = hashlib.sha1(
        ",".join(sorted(str(f.id) for f in fichas)).encode()
    ).hexdigest()[:8]
    nome_xlsx = f"consolidado-{cliente.id.hex[:8]}-{hash_sufixo}.xlsx"

    # Import local pra evitar ciclo
    from app.services.lote import LoteService
    from app.services.processamento import processar_lote

    lote_service = LoteService(db)
    lote, importacao = await lote_service.criar_a_partir_de_upload(
        conteudo=xlsx_bytes,
        nome_arquivo=nome_xlsx,
        cliente=cliente,
        enviado_por=usuario,
    )

    if referencia:
        lote.referencia = referencia
    else:
        meta_primeira = fichas[0].metadados or {}
        comp = meta_primeira.get("competencia")
        lote.referencia = (
            f"Consolidado {comp}" if comp else f"Consolidado {len(fichas)} fichas"
        )

    # Liga cada ficha ao novo lote
    for ficha in fichas:
        ficha.lote_gerado_id = lote.id
        ficha.status = StatusFicha.CONVERTIDA
        if ficha.revisado_por_id is None:
            ficha.revisado_por_id = usuario.id
            ficha.revisado_at = datetime.utcnow()

    await db.flush()

    # Dispara processamento (cria os Pagamentos com casamento de Beneficiario)
    try:
        await processar_lote(db, lote, importacao.linhas)
        await db.flush()
    except Exception:  # noqa: BLE001
        log.exception(
            "consolidacao.processar_lote_falhou",
            lote_id=str(lote.id),
            fichas=[str(f.id) for f in fichas],
        )

    log.info(
        "consolidacao.gerou_lote",
        lote_id=str(lote.id),
        cliente_id=str(cliente.id),
        qtd_fichas=len(fichas),
        qtd_linhas=len(linhas_consolidadas),
    )

    return lote


# ============================================================
# Helpers internos
# ============================================================


async def _carregar_fichas_pendentes(
    db: AsyncSession, *, cliente_id: UUID
) -> list[FichaPlantao]:
    result = await db.execute(
        select(FichaPlantao)
        .where(
            FichaPlantao.cliente_id == cliente_id,
            FichaPlantao.status.in_(
                [StatusFicha.EXTRAIDA, StatusFicha.REVISADA]
            ),
        )
        .options(selectinload(FichaPlantao.cliente))
        .order_by(FichaPlantao.created_at.desc())
    )
    return list(result.scalars())


def _nome_cliente(
    fichas_filtradas: list[FichaPlantao],
    fichas_fallback: list[FichaPlantao],
) -> str:
    for lista in (fichas_filtradas, fichas_fallback):
        if lista:
            return lista[0].cliente.nome if lista[0].cliente else "—"
    return "—"


async def _montar_extrato(
    db: AsyncSession,
    *,
    cliente_id: UUID,
    cliente_nome: str,
    titulo: str,
    chave: str,
    fichas: list[FichaPlantao],
    filtro_cpf_hash: str | None = None,
) -> ExtratoConsolidado:
    """Junta linhas das fichas, agrega por médico, marca casamento com benef."""
    # Coleta linhas (filtrando por CPF se for view "por medico")
    linhas: list[dict[str, Any]] = []
    for ficha in fichas:
        for linha in ficha.linhas_extraidas or []:
            if not _eh_linha_valida(linha):
                continue
            if filtro_cpf_hash and _cpf_hash(linha) != filtro_cpf_hash:
                continue
            linhas.append(linha)

    # Mapa cpf_hash → beneficiario_id (1 query)
    hashes = {h for h in (_cpf_hash(linha) for linha in linhas) if h}
    mapa_beneficiarios: dict[str, UUID] = {}
    if hashes:
        ben_q = await db.execute(
            select(Beneficiario.id, Beneficiario.cpf_hash).where(
                Beneficiario.cliente_id == cliente_id,
                Beneficiario.ativo.is_(True),
                Beneficiario.cpf_hash.in_(hashes),
            )
        )
        mapa_beneficiarios = {row.cpf_hash: row.id for row in ben_q.all()}

    # Agrupa por CPF
    medicos_dict: dict[str, MedicoNoExtrato] = {}
    nao_cadastrados = 0
    for linha in linhas:
        h = _cpf_hash(linha)
        if not h:
            continue
        ben_id = mapa_beneficiarios.get(h)
        cpf_mask = _mascarar_cpf(linha.get("cpf") or "")
        if h not in medicos_dict:
            if ben_id is None:
                nao_cadastrados += 1
            medicos_dict[h] = MedicoNoExtrato(
                cpf_mascarado=cpf_mask,
                nome=str(linha.get("nome") or "—").strip(),
                qtd_aparicoes=0,
                valor_total_centavos=0,
                beneficiario_id=ben_id,
                beneficiario_cadastrado=ben_id is not None,
            )
        m = medicos_dict[h]
        m.qtd_aparicoes += 1
        m.valor_total_centavos += int(linha.get("valor_centavos") or 0)

    medicos = sorted(
        medicos_dict.values(), key=lambda x: x.valor_total_centavos, reverse=True
    )

    # Resumo de cada ficha
    fichas_resumo = [
        FichaResumo(
            id=f.id,
            nome_arquivo=f.nome_arquivo,
            status=f.status.value,
            qtd_linhas=len(
                [linha for linha in (f.linhas_extraidas or []) if _eh_linha_valida(linha)]
            ),
            valor_total_centavos=sum(
                int(linha.get("valor_centavos") or 0)
                for linha in (f.linhas_extraidas or [])
                if _eh_linha_valida(linha)
                and (
                    filtro_cpf_hash is None
                    or _cpf_hash(linha) == filtro_cpf_hash
                )
            ),
            competencia=_competencia_da_ficha(f),
            hospital=(f.metadados or {}).get("hospital"),
            coordenador=(f.metadados or {}).get("coordenador"),
            created_at=f.created_at,
        )
        for f in fichas
    ]

    return ExtratoConsolidado(
        titulo=titulo,
        cliente_id=cliente_id,
        cliente_nome=cliente_nome,
        chave_agrupamento=chave,
        fichas=fichas_resumo,
        medicos=medicos,
        total_fichas=len(fichas),
        total_linhas=len(linhas),
        total_medicos_unicos=len(medicos),
        valor_total_centavos=sum(m.valor_total_centavos for m in medicos),
        medicos_nao_cadastrados=nao_cadastrados,
    )


def _mascarar_cpf(cpf: str) -> str:
    digits = re.sub(r"\D", "", cpf)
    if len(digits) >= 11:
        return f"{digits[:3]}.***.***-{digits[-2:]}"
    return "***"


def _linhas_para_xlsx(linhas: Iterable[dict[str, Any]]) -> bytes:
    """Gera XLSX in-memory no formato esperado pelo `importar_planilha`."""
    wb = Workbook()
    ws = wb.active
    if ws is None:
        ws = wb.create_sheet("Pagamentos")
    ws.title = "Pagamentos"  # type: ignore[union-attr]
    ws.append(  # type: ignore[union-attr]
        ["CPF", "Nome", "Valor", "Banco", "Agência", "Conta", "Chave PIX"]
    )
    for linha in linhas:
        valor = (linha.get("valor_centavos") or 0) / 100
        ws.append(  # type: ignore[union-attr]
            [
                linha.get("cpf", ""),
                linha.get("nome", ""),
                f"{valor:.2f}".replace(".", ","),
                linha.get("banco_codigo", "") or "",
                linha.get("agencia", "") or "",
                linha.get("conta", "") or "",
                linha.get("chave_pix", "") or "",
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ============================================================
# Auxiliar: listar competências disponíveis pra dropdown
# ============================================================


async def listar_competencias_disponiveis(
    db: AsyncSession, *, cliente_id: UUID
) -> list[str]:
    """Retorna competências (MM/YYYY) que aparecem em fichas pendentes
    do cliente, ordenadas (mais recente primeiro).
    """
    fichas = await _carregar_fichas_pendentes(db, cliente_id=cliente_id)
    competencias: set[str] = set()
    for f in fichas:
        comp = _competencia_da_ficha(f)
        if comp:
            competencias.add(comp)
        # fallback: usa mês de upload
        competencias.add(_competencia_de_data(f.created_at))
    # Ordenação cronológica reversa
    def chave_ord(s: str) -> tuple[int, int]:
        try:
            m, a = s.split("/")
            return (int(a), int(m))
        except Exception:
            return (0, 0)

    return sorted(competencias, key=chave_ord, reverse=True)


async def listar_clientes_com_fichas_pendentes(
    db: AsyncSession,
) -> list[tuple[UUID, str, int]]:
    """Pra dropdown da tela: cliente_id, nome, qtd_fichas_pendentes."""
    from app.models.cliente import Cliente

    result = await db.execute(
        select(
            Cliente.id,
            Cliente.nome,
            func.count(FichaPlantao.id).label("qtd"),
        )
        .join(FichaPlantao, FichaPlantao.cliente_id == Cliente.id)
        .where(
            FichaPlantao.status.in_(
                [StatusFicha.EXTRAIDA, StatusFicha.REVISADA]
            ),
            Cliente.deleted_at.is_(None),
        )
        .group_by(Cliente.id, Cliente.nome)
        .order_by(func.count(FichaPlantao.id).desc())
    )
    return [(row.id, row.nome, int(row.qtd)) for row in result.all()]


__all__ = [
    "ExtratoConsolidado",
    "FichaResumo",
    "FichasIncompativeisError",
    "MedicoNoExtrato",
    "consolidar_por_dia",
    "consolidar_por_hospital_mes",
    "consolidar_por_medico",
    "gerar_lote_consolidado",
    "listar_clientes_com_fichas_pendentes",
    "listar_competencias_disponiveis",
]
