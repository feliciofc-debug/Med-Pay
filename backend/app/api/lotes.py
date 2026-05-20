"""Rotas de Lote — upload, listagem, revisão, aprovação, download CNAB."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, get_db, require_aprovador
from app.core.exceptions import (
    LoteNaoEncontradoError,
    ValidacaoError,
)
from app.models.cliente import Cliente
from app.models.lote import StatusLote
from app.models.user import User
from app.schemas.lote import (
    AprovacaoResponse,
    AprovarLoteRequest,
    LoteDetalhe,
    LoteResumo,
    UploadLoteResponse,
)
from app.services.conciliacao import ConciliacaoService
from app.services.lote import LoteService

router = APIRouter()


# ============================================================
# Upload
# ============================================================


@router.post(
    "/upload",
    response_model=UploadLoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_lote(
    cliente_id: UUID = Form(...),
    arquivo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UploadLoteResponse:
    """Faz upload de uma planilha XLSX/CSV.

    Disparará processamento em background (worker) — frontend faz polling
    de `GET /lotes/{id}` pra acompanhar status.
    """
    # Valida extensão
    if not arquivo.filename:
        raise ValidacaoError("Nome do arquivo ausente")
    ext = Path(arquivo.filename).suffix.lower()
    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise ValidacaoError(
            f"Extensão {ext} não suportada. Use: "
            f"{', '.join(settings.ALLOWED_UPLOAD_EXTENSIONS)}"
        )

    # Valida tamanho (lê pra memória, ok pra MVP até 50MB)
    conteudo = await arquivo.read()
    tamanho_mb = len(conteudo) / (1024 * 1024)
    if tamanho_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise ValidacaoError(
            f"Arquivo de {tamanho_mb:.1f}MB excede o limite de "
            f"{settings.MAX_UPLOAD_SIZE_MB}MB"
        )

    # Cliente
    cliente_q = await db.execute(select(Cliente).where(Cliente.id == cliente_id))
    cliente = cliente_q.scalar_one_or_none()
    if cliente is None:
        raise ValidacaoError("Cliente não encontrado")

    service = LoteService(db)
    lote, importacao = await service.criar_a_partir_de_upload(
        conteudo=conteudo,
        nome_arquivo=arquivo.filename,
        cliente=cliente,
        enviado_por=current_user,
    )

    # Dispara processamento em background
    try:
        from app.workers.tasks import processar_lote_task

        linhas_dict = [
            {
                "numero_linha": str(linha.numero_linha),
                "cpf_raw": linha.cpf_raw,
                "nome_raw": linha.nome_raw,
                "banco_raw": linha.banco_raw,
                "agencia_raw": linha.agencia_raw,
                "conta_raw": linha.conta_raw,
                "valor_raw": str(linha.valor_raw) if linha.valor_raw is not None else None,
            }
            for linha in importacao.linhas
        ]
        processar_lote_task.delay(str(lote.id), linhas_dict)
    except Exception:
        # Worker fora do ar não deve impedir upload — o lote fica em RECEBIDO
        # e pode ser reprocessado depois.
        pass

    return UploadLoteResponse(
        lote_id=lote.id,
        hash_conteudo=lote.hash_conteudo,
        total_linhas=importacao.total_linhas,
        status=lote.status,
        mensagem=(
            f"Lote recebido com {importacao.total_linhas} linhas. "
            f"Processamento em andamento — consulte GET /api/lotes/{lote.id}."
        ),
    )


# ============================================================
# Listagem e detalhe
# ============================================================


@router.get("/", response_model=list[LoteResumo])
async def listar_lotes(
    status_filtro: StatusLote | None = Query(None, alias="status"),
    cliente_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[LoteResumo]:
    """Lista lotes (dashboard do operador)."""
    service = LoteService(db)
    lotes = await service.listar(
        status=status_filtro,
        cliente_id=cliente_id,
        limit=limit,
        offset=offset,
    )
    return [LoteResumo.model_validate(lote) for lote in lotes]


@router.get("/{lote_id}", response_model=LoteDetalhe)
async def detalhe_lote(
    lote_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LoteDetalhe:
    """Detalhe completo do lote com lista de pagamentos."""
    service = LoteService(db)
    lote = await service.get_com_pagamentos(lote_id)
    return LoteDetalhe.model_validate(lote)


# ============================================================
# Aprovação
# ============================================================


@router.post(
    "/{lote_id}/aprovar",
    response_model=AprovacaoResponse,
)
async def aprovar_lote(
    lote_id: UUID,
    payload: AprovarLoteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    aprovador: User = Depends(require_aprovador),
) -> AprovacaoResponse:
    """Aprova um lote, gera o arquivo CNAB e devolve link de download.

    Requer perfil APROVADOR ou ADMIN.
    Confirmação dupla: o frontend envia totais que ele exibiu — só aprova
    se baterem com os totais reais (proteção anti-race-condition).
    """
    service = LoteService(db)
    cnab = await service.aprovar(
        lote_id,
        aprovador=aprovador,
        observacoes=payload.observacoes,
        confirmacao_total_centavos=payload.confirmacao_total_centavos,
        confirmacao_qtd_pagamentos=payload.confirmacao_qtd_pagamentos,
    )

    return AprovacaoResponse(
        lote_id=lote_id,
        nome_arquivo=cnab.nome_arquivo,
        hash_arquivo=cnab.hash_sha256,
        quantidade_pagamentos=cnab.quantidade_pagamentos,
        valor_total_centavos=cnab.valor_total_centavos,
        download_url=f"/api/lotes/{lote_id}/cnab",
    )


# ============================================================
# Download do CNAB
# ============================================================


@router.get("/{lote_id}/cnab")
async def download_cnab(
    lote_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Baixa o arquivo .rem CNAB 240 gerado para este lote."""
    service = LoteService(db)
    lote = await service.get(lote_id)

    if not lote.caminho_arquivo_cnab:
        raise LoteNaoEncontradoError(
            "Arquivo CNAB ainda não foi gerado para este lote"
        )

    caminho = Path(lote.caminho_arquivo_cnab)
    if not caminho.exists():
        raise LoteNaoEncontradoError(
            f"Arquivo CNAB não encontrado em disco: {caminho.name}"
        )

    return FileResponse(
        path=caminho,
        media_type="text/plain",
        filename=caminho.name,
    )


# ============================================================
# Marcar como enviado ao banco
# ============================================================


@router.post("/{lote_id}/marcar-enviado")
async def marcar_enviado(
    lote_id: UUID,
    db: AsyncSession = Depends(get_db),
    aprovador: User = Depends(require_aprovador),
) -> dict[str, str]:
    """Operador confirma que já subiu o CNAB no internet banking."""
    service = LoteService(db)
    lote = await service.marcar_enviado_ao_banco(lote_id, aprovador=aprovador)
    return {"status": lote.status.value, "lote_id": str(lote.id)}


# ============================================================
# Upload do arquivo de retorno (.ret) e conciliação
# ============================================================


@router.post("/{lote_id}/retorno")
async def upload_retorno(
    lote_id: UUID,
    arquivo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    aprovador: User = Depends(require_aprovador),
) -> dict[str, object]:
    """Upload do arquivo .ret CNAB devolvido pelo banco.

    Aplica o retorno: marca cada pagamento como PAGO ou NAO_PAGO.
    Status do lote vai para CONCILIADO.
    """
    if not arquivo.filename:
        raise ValidacaoError("Nome do arquivo ausente")

    conteudo = await arquivo.read()
    if len(conteudo) == 0:
        raise ValidacaoError("Arquivo vazio")

    service = ConciliacaoService(db)
    resultado = await service.aplicar_retorno(
        lote_id,
        conteudo=conteudo,
        nome_arquivo=arquivo.filename,
        operador=aprovador,
    )

    return {
        "success": True,
        "total_no_retorno": len(resultado.pagamentos),
        "pagos": resultado.pagos,
        "nao_pagos": resultado.nao_pagos,
    }
