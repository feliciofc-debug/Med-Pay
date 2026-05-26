"""API do fluxo de autoatendimento do médico anestesista.

Rotas montadas em `/api/anestesista/*`.

Auth de sessão é por CRM (sem usuário no sistema). O token retornado é
um JWT especial `type=anestesista` com curta duração — guarda o
`beneficiario_id` e `cliente_id` que o backend usa pra filtrar tudo.

PRIVACIDADE: toda rota autenticada filtra pelo beneficiario_id do
token. Nunca aceita o id pela URL ou pelo body.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin
from app.core.exceptions import TokenInvalidoError
from app.models.beneficiario import Beneficiario
from app.models.user import User
from app.schemas.anestesista import (
    CodigoServicoCreate,
    CodigoServicoOut,
    CrmLoginRequest,
    CrmLoginResponse,
    ImportacaoCodigosResultado,
    LancamentoCreate,
    LancamentoOut,
    LancamentosListResponse,
    MedicoOut,
)
from app.services.anestesista_service import (
    AnestesistaService,
    decode_token_anestesista,
)
from app.services.codigo_servico_importacao import (
    CodigoServicoImportacaoService,
)

router = APIRouter()


# ============================================================
# Dependência: sessão de anestesista
# ============================================================


class AnestesistaSession:
    """Identidade autenticada do médico anestesista."""

    def __init__(self, *, beneficiario_id: UUID, cliente_id: UUID, crm: str) -> None:
        self.beneficiario_id = beneficiario_id
        self.cliente_id = cliente_id
        self.crm = crm


async def get_anestesista_session(request: Request) -> AnestesistaSession:
    """Extrai a sessão do médico do header Authorization ou cookie."""
    # Cookie tem prioridade (mesmo padrão do auth principal)
    cookie_token = request.cookies.get("anestesista_token")
    header = request.headers.get("authorization", "")
    bearer = header.split(" ", 1)[1] if header.lower().startswith("bearer ") else None
    raw = cookie_token or bearer
    if not raw:
        raise TokenInvalidoError("Sessão de anestesista não informada")

    payload = decode_token_anestesista(raw)
    return AnestesistaSession(
        beneficiario_id=UUID(payload["sub"]),
        cliente_id=UUID(payload["cliente_id"]),
        crm=str(payload["crm"]),
    )


# ============================================================
# Auth (público)
# ============================================================


@router.post("/login", response_model=CrmLoginResponse)
async def login_por_crm(
    payload: CrmLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> CrmLoginResponse:
    """Inicia sessão do médico anestesista a partir do CRM.

    Retorna um token de curta duração que o front guarda em cookie/storage
    e envia em todas as chamadas seguintes.
    """
    service = AnestesistaService(db)
    medico, cliente, token, expires_in = await service.login_por_crm(
        crm=payload.crm, cliente_id=payload.cliente_id
    )
    return CrmLoginResponse(
        access_token=token,
        expires_in=expires_in,
        medico=MedicoOut(
            id=medico.id,
            nome=medico.nome,
            crm=medico.crm,
            especialidade=medico.especialidade,
            cliente_id=cliente.id,
            cliente_nome=cliente.nome,
        ),
    )


@router.get("/me", response_model=MedicoOut)
async def me(
    sess: AnestesistaSession = Depends(get_anestesista_session),
    db: AsyncSession = Depends(get_db),
) -> MedicoOut:
    """Retorna a identidade do médico autenticado (debug / refresh do front)."""
    from sqlalchemy import select

    from app.models.cliente import Cliente

    stmt = (
        select(Beneficiario, Cliente)
        .join(Cliente, Beneficiario.cliente_id == Cliente.id)
        .where(Beneficiario.id == sess.beneficiario_id)
    )
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        raise TokenInvalidoError("Médico do token não existe mais")
    med, cli = row
    return MedicoOut(
        id=med.id,
        nome=med.nome,
        crm=med.crm,
        especialidade=med.especialidade,
        cliente_id=cli.id,
        cliente_nome=cli.nome,
    )


# ============================================================
# Códigos de serviço (consulta do médico)
# ============================================================


@router.get("/codigos/{codigo}", response_model=CodigoServicoOut)
async def buscar_codigo(
    codigo: str,
    sess: AnestesistaSession = Depends(get_anestesista_session),
    db: AsyncSession = Depends(get_db),
) -> CodigoServicoOut:
    """Médico digita um código e o sistema devolve descrição + valor."""
    service = AnestesistaService(db)
    cod = await service.buscar_codigo(cliente_id=sess.cliente_id, codigo=codigo)
    return CodigoServicoOut.model_validate(cod)


@router.get("/codigos", response_model=list[CodigoServicoOut])
async def listar_codigos(
    sess: AnestesistaSession = Depends(get_anestesista_session),
    db: AsyncSession = Depends(get_db),
) -> list[CodigoServicoOut]:
    """Lista todos os códigos do cliente (pra autocomplete no front)."""
    service = AnestesistaService(db)
    codigos = await service.listar_codigos(cliente_id=sess.cliente_id)
    return [CodigoServicoOut.model_validate(c) for c in codigos]


# ============================================================
# Lançamentos (escopo: só o próprio médico)
# ============================================================


@router.post("/lancamentos", response_model=LancamentoOut, status_code=201)
async def criar_lancamento(
    payload: LancamentoCreate,
    sess: AnestesistaSession = Depends(get_anestesista_session),
    db: AsyncSession = Depends(get_db),
) -> LancamentoOut:
    """Médico lança um serviço executado.

    O `beneficiario_id` vem do TOKEN — médico não consegue lançar em
    nome de outro.
    """
    service = AnestesistaService(db)
    lanc = await service.criar_lancamento(
        beneficiario_id=sess.beneficiario_id,
        cliente_id=sess.cliente_id,
        codigo=payload.codigo,
        data_servico=payload.data_servico,
        hospital_local=payload.hospital_local,
        paciente_iniciais=payload.paciente_iniciais,
        observacoes=payload.observacoes,
    )
    return LancamentoOut.model_validate(lanc)


@router.get("/lancamentos", response_model=LancamentosListResponse)
async def listar_meus_lancamentos(
    sess: AnestesistaSession = Depends(get_anestesista_session),
    db: AsyncSession = Depends(get_db),
) -> LancamentosListResponse:
    """Lista os lançamentos do médico autenticado (escopo hard)."""
    service = AnestesistaService(db)
    items, total, total_centavos = await service.listar_meus_lancamentos(
        beneficiario_id=sess.beneficiario_id,
        cliente_id=sess.cliente_id,
    )
    return LancamentosListResponse(
        items=[LancamentoOut.model_validate(i) for i in items],
        total=total,
        total_centavos=total_centavos,
    )


@router.delete("/lancamentos/{lancamento_id}", response_model=LancamentoOut)
async def cancelar_lancamento(
    lancamento_id: UUID,
    sess: AnestesistaSession = Depends(get_anestesista_session),
    db: AsyncSession = Depends(get_db),
) -> LancamentoOut:
    """Médico cancela seu próprio lançamento (só se ainda LANCADO)."""
    service = AnestesistaService(db)
    lanc = await service.cancelar_lancamento(
        lancamento_id=lancamento_id,
        beneficiario_id=sess.beneficiario_id,
    )
    return LancamentoOut.model_validate(lanc)


# ============================================================
# Admin: gestão da tabela de códigos
# ============================================================


@router.post(
    "/admin/clientes/{cliente_id}/codigos",
    response_model=CodigoServicoOut,
    status_code=201,
)
async def admin_criar_codigo(
    cliente_id: UUID,
    payload: CodigoServicoCreate,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> CodigoServicoOut:
    """Admin BPO cria manualmente um código pra um cliente."""
    service = AnestesistaService(db)
    cod = await service.criar_codigo(
        cliente_id=cliente_id,
        codigo=payload.codigo,
        descricao=payload.descricao,
        valor_centavos=payload.valor_centavos,
        categoria=payload.categoria,
        porte=payload.porte,
        observacoes=payload.observacoes,
    )
    return CodigoServicoOut.model_validate(cod)


@router.get(
    "/admin/clientes/{cliente_id}/codigos",
    response_model=list[CodigoServicoOut],
)
async def admin_listar_codigos(
    cliente_id: UUID,
    incluir_inativos: bool = False,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[CodigoServicoOut]:
    """Admin BPO lista todos os códigos do cliente (inclui inativos opcional)."""
    service = AnestesistaService(db)
    codigos = await service.listar_codigos(
        cliente_id=cliente_id,
        somente_ativos=not incluir_inativos,
    )
    return [CodigoServicoOut.model_validate(c) for c in codigos]


@router.post(
    "/admin/clientes/{cliente_id}/codigos/importar",
    response_model=ImportacaoCodigosResultado,
)
async def admin_importar_codigos(
    cliente_id: UUID,
    arquivo: UploadFile = File(..., description="XLSX/CSV com colunas código, descrição e valor"),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ImportacaoCodigosResultado:
    """Admin BPO importa a planilha de códigos do cliente.

    O importador é tolerante: detecta colunas por sinônimos (código,
    descrição, valor, categoria, porte). Re-importação faz upsert por
    (cliente_id, codigo) — atualiza valores em vez de duplicar.
    """
    conteudo = await arquivo.read()
    service = CodigoServicoImportacaoService(db)
    resultado = await service.importar(
        cliente_id=cliente_id,
        conteudo=conteudo,
        nome_arquivo=arquivo.filename or "planilha.xlsx",
    )
    return ImportacaoCodigosResultado(
        criados=resultado.criados,
        atualizados=resultado.atualizados,
        inalterados=resultado.inalterados,
        erros=resultado.erros,
        total_linhas=resultado.total_linhas,
    )


__all__ = ["router"]
