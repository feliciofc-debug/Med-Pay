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
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import (
    get_current_user,
    get_db,
    require_aprovador,
    require_feature,
)
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

    # Estratégia de processamento:
    # 1) Tenta enfileirar via Celery (worker em background — bom pra lotes
    #    muito grandes em produção).
    # 2) Se Celery não estiver disponível (broker fora do ar, TLS do Redis
    #    quebrado, etc.), processa INLINE na própria request. Pra os
    #    volumes típicos (até alguns milhares de linhas) isso é rápido.
    #
    # Decisão consciente: garantir que o usuário sempre veja o resultado,
    # mesmo que o worker esteja com problema. Em produção real, religar
    # o Celery e remover o fallback inline.
    celery_ok = False
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
        celery_ok = True
    except Exception:
        celery_ok = False

    if not celery_ok:
        # Fallback síncrono — processa antes de devolver
        from app.services.processamento import processar_lote

        try:
            await processar_lote(db, lote, importacao.linhas)
            await db.flush()
        except Exception as exc:  # pragma: no cover
            # Se até o fallback falhou, mantém o lote em RECEBIDO pra retry manual
            from app.models.lote import StatusLote

            lote.status = StatusLote.ERRO
            lote.mensagem_erro = f"Falha no processamento: {exc}"

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


@router.get("", response_model=list[LoteResumo])
async def listar_lotes(
    status_filtro: StatusLote | None = Query(None, alias="status"),
    cliente_id: UUID | None = Query(None),
    enviado_por_id: UUID | None = Query(None, alias="operador"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[LoteResumo]:
    """Lista lotes (dashboard do operador).

    Multi-tenancy: se o user tem `cliente_id`, força o filtro pra
    esse cliente (ignora o query param `cliente_id` mesmo se vier).
    MedPag interno (sem cliente_id) pode filtrar livre.
    """
    if current_user.cliente_id is not None:
        cliente_id = current_user.cliente_id
    service = LoteService(db)
    lotes = await service.listar(
        status=status_filtro,
        cliente_id=cliente_id,
        enviado_por_id=enviado_por_id,
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
    from app.core.deps import verificar_acesso_cliente

    service = LoteService(db)
    lote = await service.get_com_pagamentos(lote_id)
    verificar_acesso_cliente(
        current_user,
        lote.cliente_id,
        mensagem="Lote pertence a outro cliente.",
    )
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


@router.get("/{lote_id}/cnab", dependencies=[Depends(require_feature("pagamento.cnab"))])
async def download_cnab(
    lote_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Baixa o arquivo .rem CNAB 240 gerado para este lote.

    Estratégia (em ordem):
      1. Bytes persistidos no banco (`conteudo_arquivo_cnab`).
      2. Arquivo em disco (cache local — pode sumir entre deploys).
      3. Regera on-demand a partir dos pagamentos aprovados (último recurso,
         para lotes antigos cujo arquivo perdeu antes de termos persistência
         no banco).
    """
    service = LoteService(db)
    lote = await service.get_com_pagamentos(lote_id)

    # Se o nome salvo no banco ainda está no formato antigo (com hífen/
    # underline), força regeração: bancos como a Unicred só aceitam nome
    # 100% alfanumérico. Vale também pra arquivos cujo conteúdo foi gerado
    # antes do fix do sequencial dos segmentos.
    nome_invalido = (
        lote.nome_arquivo_cnab is not None
        and not lote.nome_arquivo_cnab.replace(".", "").isalnum()
    )
    if nome_invalido and lote.status in (
        StatusLote.APROVADO,
        StatusLote.ENVIADO_BANCO,
    ):
        lote.conteudo_arquivo_cnab = None
        lote.nome_arquivo_cnab = None
        lote.hash_arquivo_cnab = None

    nome_arquivo = (
        lote.nome_arquivo_cnab or f"MEDPAG{lote.id.hex[:8].upper()}.REM"
    )

    # 1) Banco
    if lote.conteudo_arquivo_cnab:
        return Response(
            content=bytes(lote.conteudo_arquivo_cnab),
            media_type="text/plain; charset=latin-1",
            headers={
                "Content-Disposition": f'attachment; filename="{nome_arquivo}"'
            },
        )

    # 2) Disco
    if lote.caminho_arquivo_cnab:
        caminho = Path(lote.caminho_arquivo_cnab)
        if caminho.exists():
            return FileResponse(
                path=caminho,
                media_type="text/plain; charset=latin-1",
                filename=caminho.name,
            )

    # 3) Regera (lote tem que estar aprovado)
    if lote.status not in (StatusLote.APROVADO, StatusLote.ENVIADO_BANCO):
        raise LoteNaoEncontradoError(
            "Arquivo CNAB ainda não foi gerado para este lote"
        )

    bytes_gerados, nome_gerado = await service.regerar_cnab(lote)
    return Response(
        content=bytes_gerados,
        media_type="text/plain; charset=latin-1",
        headers={
            "Content-Disposition": f'attachment; filename="{nome_gerado}"'
        },
    )


# ============================================================
# Download da lista PIX (XLSX) — pagamentos PIX deste lote
# ============================================================


@router.get("/{lote_id}/pix.xlsx")
async def download_lista_pix(
    lote_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Baixa planilha com os pagamentos PIX aprovados deste lote.

    PIX não entra no CNAB Unicred (layout PIX não homologado no convênio).
    A planilha tem: Nome, CPF (mascarado), Chave PIX, Valor. O financeiro
    do hospital usa para pagar via Internet Banking ou enviar para a
    operadora de PIX em lote (Asaas etc.).
    """
    import io

    import pandas as pd

    from app.models.pagamento import ModalidadePagamento, StatusPagamento

    service = LoteService(db)
    lote = await service.get_com_pagamentos(lote_id)

    pix = [
        p
        for p in lote.pagamentos
        if p.modalidade == ModalidadePagamento.PIX
        and p.status in (StatusPagamento.APROVADO, StatusPagamento.VALIDO)
    ]
    if not pix:
        raise ValidacaoError(
            "Este lote não tem pagamentos PIX. Use 'Baixar CNAB' para pagamentos TED."
        )

    total_centavos = sum(p.valor_centavos for p in pix)
    rows = []
    for p in pix:
        rows.append(
            {
                "Linha": p.linha_planilha,
                "Nome": p.nome,
                "CPF": p.cpf_mascarado,
                "Chave PIX": p.chave_pix or "",
                "Valor (R$)": f"{p.valor_centavos / 100:.2f}".replace(".", ","),
                "Status": p.status.value,
            }
        )
    # linha total
    rows.append(
        {
            "Linha": "",
            "Nome": "TOTAL",
            "CPF": "",
            "Chave PIX": "",
            "Valor (R$)": f"{total_centavos / 100:.2f}".replace(".", ","),
            "Status": "",
        }
    )

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="PIX")
    conteudo = buf.getvalue()

    nome_arquivo = f"MEDPAG-PIX-{lote.id.hex[:8].upper()}.xlsx"
    return Response(
        content=conteudo,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{nome_arquivo}"'
        },
    )


# ============================================================
# Regerar CNAB (forçar geração nova)
# ============================================================


@router.post("/{lote_id}/cnab/regerar")
async def regerar_cnab(
    lote_id: UUID,
    db: AsyncSession = Depends(get_db),
    aprovador: User = Depends(require_aprovador),
) -> dict[str, str | int]:
    """Força a regeração do CNAB com o sequencial atual da empresa.

    Caso de uso: banco rejeitou o arquivo (ex.: sequencial fora de ordem),
    operador ajusta `proximo_numero_sequencial` em Empresa Pagadora e
    pede o arquivo novo aqui. Limpa o conteúdo armazenado e gera de novo.
    """
    service = LoteService(db)
    lote = await service.get_com_pagamentos(lote_id)

    if lote.status not in (StatusLote.APROVADO, StatusLote.ENVIADO_BANCO):
        raise LoteNaoEncontradoError(
            f"Lote em status {lote.status.value} não tem CNAB para regerar"
        )

    lote.conteudo_arquivo_cnab = None
    lote.nome_arquivo_cnab = None
    lote.hash_arquivo_cnab = None
    lote.caminho_arquivo_cnab = None

    bytes_gerados, nome_gerado = await service.regerar_cnab(lote)
    return {
        "lote_id": str(lote.id),
        "nome_arquivo": nome_gerado,
        "tamanho_bytes": len(bytes_gerados),
        "hash_arquivo": lote.hash_arquivo_cnab or "",
    }


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
