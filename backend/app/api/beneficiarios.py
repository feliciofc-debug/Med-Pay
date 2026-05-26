"""API do cadastro mestre de beneficiários (prestadores).

Operações:
    - Listar (com filtros) / detalhar
    - Criar manual / atualizar / aprovar / desativar
    - Importar planilha em 2 passos (preview → confirma)

Permissão:
    - Operações de leitura: qualquer usuário com visão executiva
      (admin, aprovador, operador). Coordenador NÃO acessa.
    - Operações de escrita: ADMIN ou APROVADOR (no fluxo do MedPag,
      cadastrar prestador é decisão de negócio que requer responsabilidade
      pela qualidade dos dados bancários).
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    get_db,
    require_aprovador,
    require_visao_executiva,
)
from app.core.exceptions import ValidacaoError
from app.models.beneficiario import StatusBeneficiario
from app.models.user import User
from app.schemas.beneficiario import (
    BeneficiarioCreateRequest,
    BeneficiarioListResponse,
    BeneficiarioOut,
    BeneficiarioUpdateRequest,
    ImportConfirmRequest,
    ImportConfirmResponse,
    ImportPreviewResponse,
)
from app.services.beneficiario_service import (
    BeneficiarioNaoEncontradoError,
    BeneficiarioService,
    BeneficiarioServiceError,
    ClienteNaoEncontradoError,
)

log = structlog.get_logger()

router = APIRouter(prefix="/api/beneficiarios", tags=["beneficiarios"])


# ============================================================
# Listagem e detalhe
# ============================================================


@router.get("", response_model=BeneficiarioListResponse)
async def listar_beneficiarios(
    cliente_id: UUID | None = Query(default=None),
    status_filter: StatusBeneficiario | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_visao_executiva),
) -> BeneficiarioListResponse:
    service = BeneficiarioService(db)
    return await service.listar(
        cliente_id=cliente_id,
        status=status_filter,
        search=search,
        page=page,
        per_page=per_page,
    )


@router.get("/{beneficiario_id}", response_model=BeneficiarioOut)
async def detalhar_beneficiario(
    beneficiario_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_visao_executiva),
) -> BeneficiarioOut:
    service = BeneficiarioService(db)
    try:
        b = await service.buscar(beneficiario_id)
    except BeneficiarioNaoEncontradoError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return BeneficiarioOut.model_validate(b)


# ============================================================
# Criar / atualizar / aprovar / desativar
# ============================================================


@router.post(
    "",
    response_model=BeneficiarioOut,
    status_code=status.HTTP_201_CREATED,
)
async def criar_beneficiario(
    payload: BeneficiarioCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_aprovador),
) -> BeneficiarioOut:
    service = BeneficiarioService(db)
    try:
        b = await service.criar(payload)
    except ClienteNaoEncontradoError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except BeneficiarioServiceError as e:
        raise ValidacaoError(str(e)) from e
    log.info(
        "beneficiario.criado",
        beneficiario_id=str(b.id),
        cliente_id=str(b.cliente_id),
        criador=user.email,
    )
    return BeneficiarioOut.model_validate(b)


@router.patch("/{beneficiario_id}", response_model=BeneficiarioOut)
async def atualizar_beneficiario(
    beneficiario_id: UUID,
    payload: BeneficiarioUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_aprovador),
) -> BeneficiarioOut:
    service = BeneficiarioService(db)
    try:
        b = await service.atualizar(beneficiario_id, payload)
    except BeneficiarioNaoEncontradoError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except BeneficiarioServiceError as e:
        raise ValidacaoError(str(e)) from e
    log.info(
        "beneficiario.atualizado",
        beneficiario_id=str(b.id),
        atualizador=user.email,
    )
    return BeneficiarioOut.model_validate(b)


@router.post("/{beneficiario_id}/aprovar", response_model=BeneficiarioOut)
async def aprovar_beneficiario(
    beneficiario_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_aprovador),
) -> BeneficiarioOut:
    service = BeneficiarioService(db)
    try:
        b = await service.aprovar(beneficiario_id)
    except BeneficiarioNaoEncontradoError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    log.info(
        "beneficiario.aprovado",
        beneficiario_id=str(b.id),
        aprovador=user.email,
    )
    return BeneficiarioOut.model_validate(b)


@router.post("/{beneficiario_id}/desativar", response_model=BeneficiarioOut)
async def desativar_beneficiario(
    beneficiario_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_aprovador),
) -> BeneficiarioOut:
    service = BeneficiarioService(db)
    try:
        b = await service.desativar(beneficiario_id)
    except BeneficiarioNaoEncontradoError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    log.info(
        "beneficiario.desativado",
        beneficiario_id=str(b.id),
        ator=user.email,
    )
    return BeneficiarioOut.model_validate(b)


# ============================================================
# Importação em massa (XLSX/CSV)
# ============================================================


@router.post(
    "/import/preview",
    response_model=ImportPreviewResponse,
)
async def preview_importacao(
    cliente_id: UUID = Form(...),
    arquivo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_aprovador),
) -> ImportPreviewResponse:
    """Recebe a planilha e devolve um relatório linha-a-linha com erros e
    avisos. Nada é gravado ainda — usuário revisa e chama /import/confirm.
    """
    if not arquivo.filename:
        raise ValidacaoError("Nome do arquivo é obrigatório.")
    conteudo = await arquivo.read()
    if not conteudo:
        raise ValidacaoError("Arquivo vazio.")

    service = BeneficiarioService(db)
    try:
        return await service.importar_preview(
            cliente_id=cliente_id,
            conteudo=conteudo,
            nome_arquivo=arquivo.filename,
        )
    except ClienteNaoEncontradoError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except BeneficiarioServiceError as e:
        raise ValidacaoError(str(e)) from e


@router.post(
    "/import/confirm",
    response_model=ImportConfirmResponse,
)
async def confirmar_importacao(
    payload: ImportConfirmRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_aprovador),
) -> ImportConfirmResponse:
    """Confirma e efetiva a importação previamente analisada via /preview."""
    service = BeneficiarioService(db)
    try:
        resultado = await service.importar_confirmar(payload)
    except ClienteNaoEncontradoError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except BeneficiarioServiceError as e:
        raise ValidacaoError(str(e)) from e

    log.info(
        "beneficiario.import.confirmado",
        criados=resultado.qtd_criados,
        atualizados=resultado.qtd_atualizados,
        ignorados=resultado.qtd_ignorados,
        erros=resultado.qtd_erros,
        ator=user.email,
    )
    return resultado


__all__ = ["router"]
