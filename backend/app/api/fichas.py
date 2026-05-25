"""Rotas REST de Fichas de Plantão (módulo de OCR).

Fluxo do coordenador:
    POST   /api/fichas/upload          → sobe foto/PDF, OCR roda inline
    GET    /api/fichas                 → lista para o aprovador conferir
    GET    /api/fichas/{id}            → detalhe (texto OCR + linhas)
    PUT    /api/fichas/{id}/linhas     → revisor edita as linhas
    POST   /api/fichas/{id}/reprocessar → re-roda o OCR
    POST   /api/fichas/{id}/converter  → vira lote de pagamento
    GET    /api/fichas/{id}/arquivo    → baixa o arquivo original
    DELETE /api/fichas/{id}            → remove (se não virou lote)
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import (
    get_current_user,
    get_db,
    require_aprovador,
    require_pode_subir_ficha,
)
from app.core.exceptions import PermissaoNegadaError, ValidacaoError
from app.models.cliente import Cliente
from app.models.ficha_plantao import StatusFicha
from app.models.user import User, UserRole
from app.schemas.ficha import (
    AtualizarLinhasRequest,
    ConverterEmLoteResponse,
    FichaDetalhe,
    FichaResumo,
    LinhaExtraidaSchema,
)
from app.services.ficha import EXTENSOES_SUPORTADAS, FichaService

router = APIRouter()


def _ficha_para_resumo(ficha) -> FichaResumo:  # type: ignore[no-untyped-def]
    """Serializa um FichaPlantao em FichaResumo (campos derivados)."""
    return FichaResumo.model_validate(
        {
            "id": ficha.id,
            "cliente": {
                "id": ficha.cliente.id,
                "nome": ficha.cliente.nome,
                "cnpj": ficha.cliente.cnpj,
            },
            "nome_arquivo": ficha.nome_arquivo,
            "mime_type": ficha.mime_type,
            "tamanho_bytes": ficha.tamanho_bytes,
            "status": ficha.status,
            "paginas_ocr": ficha.paginas_ocr,
            "total_linhas": ficha.total_linhas,
            "valor_total_centavos": ficha.valor_total_centavos,
            "mensagem_erro": ficha.mensagem_erro,
            "lote_gerado_id": ficha.lote_gerado_id,
            "created_at": ficha.created_at,
            "revisado_at": ficha.revisado_at,
        }
    )


def _ficha_para_detalhe(ficha) -> FichaDetalhe:  # type: ignore[no-untyped-def]
    base = _ficha_para_resumo(ficha).model_dump()
    base["texto_ocr"] = ficha.texto_ocr
    base["linhas_extraidas"] = [
        LinhaExtraidaSchema(**linha) for linha in (ficha.linhas_extraidas or [])
    ]
    base["metadados"] = ficha.metadados
    return FichaDetalhe.model_validate(base)


# ============================================================
# Upload
# ============================================================


@router.post(
    "/upload",
    response_model=FichaDetalhe,
    status_code=status.HTTP_201_CREATED,
)
async def upload_ficha(
    cliente_id: UUID = Form(...),
    arquivo: UploadFile = File(...),
    executar_ocr: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_pode_subir_ficha),
) -> FichaDetalhe:
    """Recebe a foto/PDF da ficha carimbada e dispara OCR inline.

    Para imagens com até ~3MB e PDFs até 3 páginas, o OCR é síncrono
    (5-15s). Para volumes maiores, usar `executar_ocr=false` e chamar
    `POST /fichas/{id}/reprocessar` depois (async via worker no futuro).
    """
    if not arquivo.filename:
        raise ValidacaoError("Nome do arquivo ausente")

    ext = Path(arquivo.filename).suffix.lower().lstrip(".")
    if ext not in EXTENSOES_SUPORTADAS:
        raise ValidacaoError(
            f"Formato '{ext}' não suportado. "
            f"Use: {', '.join(sorted(EXTENSOES_SUPORTADAS))}."
        )

    conteudo = await arquivo.read()
    tamanho_mb = len(conteudo) / (1024 * 1024)
    if tamanho_mb > settings.OCR_MAX_FILE_MB:
        raise ValidacaoError(
            f"Arquivo de {tamanho_mb:.1f}MB excede o limite de "
            f"{settings.OCR_MAX_FILE_MB}MB do plano OCR. "
            "Reduza a resolução ou divida o PDF."
        )

    cliente_q = await db.execute(select(Cliente).where(Cliente.id == cliente_id))
    cliente = cliente_q.scalar_one_or_none()
    if cliente is None:
        raise ValidacaoError("Cliente não encontrado")

    mime = arquivo.content_type or "application/octet-stream"

    service = FichaService(db)
    ficha = await service.criar_a_partir_de_upload(
        conteudo=conteudo,
        nome_arquivo=arquivo.filename,
        mime_type=mime,
        cliente=cliente,
        enviado_por=current_user,
        executar_ocr=executar_ocr,
    )

    # Recarrega com cliente eager pra serialização
    ficha = await service.get(ficha.id)
    return _ficha_para_detalhe(ficha)


# ============================================================
# Listagem
# ============================================================


@router.get("", response_model=list[FichaResumo])
async def listar_fichas(
    status_filtro: StatusFicha | None = Query(None, alias="status"),
    cliente_id: UUID | None = Query(None),
    enviado_por_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[FichaResumo]:
    # Coordenador só vê o que ele subiu — força o filtro mesmo se vier
    # outro `enviado_por_id` no querystring.
    if current_user.role == UserRole.COORDENADOR:
        enviado_por_id = current_user.id

    service = FichaService(db)
    fichas = await service.listar(
        status=status_filtro,
        cliente_id=cliente_id,
        enviado_por_id=enviado_por_id,
        limit=limit,
        offset=offset,
    )
    return [_ficha_para_resumo(f) for f in fichas]


@router.get("/{ficha_id}", response_model=FichaDetalhe)
async def detalhar_ficha(
    ficha_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FichaDetalhe:
    service = FichaService(db)
    ficha = await service.get(ficha_id)
    # Coordenador só pode abrir as fichas que ele mesmo enviou.
    if (
        current_user.role == UserRole.COORDENADOR
        and ficha.enviado_por_id != current_user.id
    ):
        raise PermissaoNegadaError("Esta ficha não pertence a você")
    return _ficha_para_detalhe(ficha)


# ============================================================
# Edição manual
# ============================================================


@router.put("/{ficha_id}/linhas", response_model=FichaDetalhe)
async def atualizar_linhas(
    ficha_id: UUID,
    payload: AtualizarLinhasRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FichaDetalhe:
    service = FichaService(db)
    linhas_dict = [linha.model_dump() for linha in payload.linhas]
    ficha = await service.atualizar_linhas(
        ficha_id,
        linhas=linhas_dict,
        metadados=payload.metadados,
        revisor=current_user,
    )
    ficha = await service.get(ficha.id)
    return _ficha_para_detalhe(ficha)


@router.post("/{ficha_id}/reprocessar", response_model=FichaDetalhe)
async def reprocessar_ocr(
    ficha_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FichaDetalhe:
    service = FichaService(db)
    ficha = await service.reexecutar_ocr(ficha_id)
    ficha = await service.get(ficha.id)
    return _ficha_para_detalhe(ficha)


# ============================================================
# Conversão em lote
# ============================================================


@router.post("/{ficha_id}/converter", response_model=ConverterEmLoteResponse)
async def converter_em_lote(
    ficha_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_aprovador),
) -> ConverterEmLoteResponse:
    """Gera um lote de pagamento a partir das linhas revisadas da ficha.

    Após sucesso, a ficha vai pra status CONVERTIDA e fica linkada via
    `lote_gerado_id`. O lote nasce em RECEBIDO e segue o pipeline normal
    (validação → AGUARDANDO_REVISAO → APROVADO → CNAB).
    """
    service = FichaService(db)
    lote = await service.converter_em_lote(ficha_id, usuario=current_user)
    return ConverterEmLoteResponse(
        lote_id=lote.id,
        qtd_pagamentos=lote.total_pagamentos,
    )


# ============================================================
# Download do arquivo original
# ============================================================


@router.get("/{ficha_id}/arquivo")
async def baixar_arquivo_original(
    ficha_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Response:
    service = FichaService(db)
    ficha = await service.get(ficha_id)
    return Response(
        content=ficha.arquivo_bytes,
        media_type=ficha.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{ficha.nome_arquivo}"',
        },
    )


# ============================================================
# Delete
# ============================================================


@router.delete("/{ficha_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def deletar_ficha(
    ficha_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Response:
    service = FichaService(db)
    await service.deletar(ficha_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
