"""Rotas REST de Fichas de Plantão (módulo de OCR).

Fluxo do coordenador:
    POST   /api/fichas/upload           → sobe foto/PDF, OCR roda inline
    POST   /api/fichas/upload-lote      → sobe ZIP com várias fichas dentro
    GET    /api/fichas                  → lista para o aprovador conferir
    GET    /api/fichas/{id}             → detalhe (texto OCR + linhas)
    PUT    /api/fichas/{id}/linhas      → revisor edita as linhas
    POST   /api/fichas/{id}/reprocessar → re-roda o OCR
    POST   /api/fichas/{id}/converter   → vira lote de pagamento
    GET    /api/fichas/{id}/arquivo     → baixa o arquivo original
    DELETE /api/fichas/{id}             → remove (se não virou lote)
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from uuid import UUID

import structlog
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
from pydantic import BaseModel
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

log = structlog.get_logger()

# Limites do upload em lote (ZIP)
ZIP_MAX_FICHAS = 50
ZIP_MAX_SIZE_MB = 100

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
        _hidratar_linha_schema(linha) for linha in (ficha.linhas_extraidas or [])
    ]
    base["metadados"] = ficha.metadados
    return FichaDetalhe.model_validate(base)


def _hidratar_linha_schema(linha_raw: dict) -> LinhaExtraidaSchema:  # type: ignore[type-arg]
    """Carrega uma linha do JSON e recalcula essenciais_faltantes/esta_pronta.

    Recalcular sempre garante que mesmo após edição manual via PUT /linhas
    os indicadores ficam corretos sem o frontend precisar fazer essa lógica.
    """
    schema = LinhaExtraidaSchema(**linha_raw)
    faltam: list[str] = []
    if not schema.cpf:
        faltam.append("cpf")
    if not schema.nome:
        faltam.append("nome")
    if not schema.valor_centavos or schema.valor_centavos <= 0:
        faltam.append("valor")
    tem_pix = bool(schema.chave_pix)
    tem_conta = bool(schema.banco_codigo and schema.agencia and schema.conta)
    if not (tem_pix or tem_conta):
        faltam.append("forma_pagamento")
    schema.essenciais_faltantes = faltam
    schema.esta_pronta = not faltam
    return schema


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

    # Só deixa subir ficha para um cliente que o usuário realmente opera
    # (ele mesmo ou um hospital da sua carteira). Evita criar ficha que
    # depois não pode ser lida ("Ficha pertence a outro cliente").
    from app.core.deps import verificar_acesso_cliente

    await verificar_acesso_cliente(
        db,
        current_user,
        cliente_id,
        mensagem="Você não pode enviar fichas para este cliente.",
    )

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
# Upload em lote (ZIP)
# ============================================================


class FichaProcessadaItem(BaseModel):
    """Resultado individual dentro de um upload em lote."""

    nome_arquivo: str
    sucesso: bool
    ficha_id: UUID | None = None
    status: StatusFicha | None = None
    erro: str | None = None


class UploadLoteResponse(BaseModel):
    """Resumo do upload em lote (ZIP)."""

    total_arquivos: int
    sucessos: int
    falhas: int
    itens: list[FichaProcessadaItem]


def _eh_arquivo_oculto_zip(nome: str) -> bool:
    """Filtra entradas chatas de ZIP (macOS metadata, dotfiles, pastas)."""
    if nome.endswith("/"):
        return True
    base = Path(nome).name
    if not base:
        return True
    if base.startswith(".") or base.startswith("._"):
        return True
    if "__MACOSX" in nome:
        return True
    return False


@router.post(
    "/upload-lote",
    response_model=UploadLoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_ficha_lote(
    cliente_id: UUID = Form(...),
    arquivo: UploadFile = File(...),
    executar_ocr: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_pode_subir_ficha),
) -> UploadLoteResponse:
    """Aceita um ZIP contendo várias fichas (PNG/JPG/PDF) e processa todas.

    Cada arquivo dentro do ZIP é tratado como uma ficha independente:
        - Hash duplicado → ignorado com erro DUPLICADA (idempotente)
        - Formato não suportado → erro FORMATO_INVALIDO
        - OCR falhou → ficha persistida em status ERRO (revisor edita manual)
        - Sucesso → ficha persistida em status EXTRAIDA/RECEBIDA

    A response sempre traz `itens` com 1 entrada por arquivo do ZIP, mesmo
    nos erros. Assim o frontend mostra a lista completa pro coordenador.

    Limites:
        - Máximo {ZIP_MAX_FICHAS} fichas por ZIP
        - ZIP até {ZIP_MAX_SIZE_MB}MB
        - Cada ficha individualmente respeita OCR_MAX_FILE_MB
    """
    if not arquivo.filename:
        raise ValidacaoError("Nome do arquivo ausente")

    ext = Path(arquivo.filename).suffix.lower().lstrip(".")
    if ext != "zip":
        raise ValidacaoError(
            "Endpoint /upload-lote aceita apenas .zip. "
            "Para arquivos individuais use /upload."
        )

    conteudo_zip = await arquivo.read()
    tamanho_mb = len(conteudo_zip) / (1024 * 1024)
    if tamanho_mb > ZIP_MAX_SIZE_MB:
        raise ValidacaoError(
            f"ZIP de {tamanho_mb:.1f}MB excede o limite de {ZIP_MAX_SIZE_MB}MB"
        )

    cliente_q = await db.execute(select(Cliente).where(Cliente.id == cliente_id))
    cliente = cliente_q.scalar_one_or_none()
    if cliente is None:
        raise ValidacaoError("Cliente não encontrado")

    from app.core.deps import verificar_acesso_cliente

    await verificar_acesso_cliente(
        db,
        current_user,
        cliente_id,
        mensagem="Você não pode enviar fichas para este cliente.",
    )

    try:
        zf = zipfile.ZipFile(io.BytesIO(conteudo_zip))
    except zipfile.BadZipFile as exc:
        raise ValidacaoError(f"ZIP inválido ou corrompido: {exc}") from exc

    nomes_dentro = [n for n in zf.namelist() if not _eh_arquivo_oculto_zip(n)]
    if not nomes_dentro:
        raise ValidacaoError("ZIP vazio ou sem arquivos válidos")
    if len(nomes_dentro) > ZIP_MAX_FICHAS:
        raise ValidacaoError(
            f"ZIP tem {len(nomes_dentro)} arquivos — máximo é {ZIP_MAX_FICHAS}. "
            "Divida em vários ZIPs menores."
        )

    service = FichaService(db)
    itens: list[FichaProcessadaItem] = []
    sucessos = 0
    falhas = 0

    for nome in nomes_dentro:
        nome_base = Path(nome).name
        ext_item = Path(nome_base).suffix.lower().lstrip(".")

        if ext_item not in EXTENSOES_SUPORTADAS:
            itens.append(
                FichaProcessadaItem(
                    nome_arquivo=nome_base,
                    sucesso=False,
                    erro=(
                        f"Formato '{ext_item}' não suportado. "
                        f"Use: {', '.join(sorted(EXTENSOES_SUPORTADAS))}"
                    ),
                )
            )
            falhas += 1
            continue

        try:
            conteudo_item = zf.read(nome)
        except Exception as exc:  # noqa: BLE001 - queremos engolir e reportar
            itens.append(
                FichaProcessadaItem(
                    nome_arquivo=nome_base,
                    sucesso=False,
                    erro=f"Falha ao extrair do ZIP: {exc}",
                )
            )
            falhas += 1
            continue

        item_mb = len(conteudo_item) / (1024 * 1024)
        if item_mb > settings.OCR_MAX_FILE_MB:
            itens.append(
                FichaProcessadaItem(
                    nome_arquivo=nome_base,
                    sucesso=False,
                    erro=(
                        f"Arquivo de {item_mb:.1f}MB excede o limite de "
                        f"{settings.OCR_MAX_FILE_MB}MB do plano OCR"
                    ),
                )
            )
            falhas += 1
            continue

        # Mime aproximado pela extensão (UploadFile não tem por item)
        mime = {
            "pdf": "application/pdf",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "tiff": "image/tiff",
            "tif": "image/tiff",
            "bmp": "image/bmp",
            "webp": "image/webp",
        }.get(ext_item, "application/octet-stream")

        try:
            ficha = await service.criar_a_partir_de_upload(
                conteudo=conteudo_item,
                nome_arquivo=nome_base,
                mime_type=mime,
                cliente=cliente,
                enviado_por=current_user,
                executar_ocr=executar_ocr,
            )
            itens.append(
                FichaProcessadaItem(
                    nome_arquivo=nome_base,
                    sucesso=True,
                    ficha_id=ficha.id,
                    status=ficha.status,
                )
            )
            sucessos += 1
        except Exception as exc:  # noqa: BLE001 - registra a falha individual
            log.warning(
                "ficha_upload_lote_item_falhou",
                nome=nome_base,
                erro=str(exc),
            )
            itens.append(
                FichaProcessadaItem(
                    nome_arquivo=nome_base,
                    sucesso=False,
                    erro=str(exc),
                )
            )
            falhas += 1

    log.info(
        "ficha_upload_lote_concluido",
        cliente_id=str(cliente_id),
        usuario_id=str(current_user.id),
        total=len(nomes_dentro),
        sucessos=sucessos,
        falhas=falhas,
    )

    return UploadLoteResponse(
        total_arquivos=len(nomes_dentro),
        sucessos=sucessos,
        falhas=falhas,
        itens=itens,
    )


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

    # Multi-tenancy: user de cliente vê só fichas do próprio cliente
    if current_user.cliente_id is not None:
        cliente_id = current_user.cliente_id

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
    from app.core.deps import verificar_acesso_cliente

    service = FichaService(db)
    ficha = await service.get(ficha_id)
    # Coordenador só pode abrir as fichas que ele mesmo enviou.
    if (
        current_user.role == UserRole.COORDENADOR
        and ficha.enviado_por_id != current_user.id
    ):
        raise PermissaoNegadaError("Esta ficha não pertence a você")
    # Multi-tenancy: usuário de cliente só vê fichas do próprio cliente
    await verificar_acesso_cliente(
        db,
        current_user,
        ficha.cliente_id,
        mensagem="Ficha pertence a outro cliente.",
    )
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
    forcar: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_aprovador),
) -> ConverterEmLoteResponse:
    """Gera um lote de pagamento a partir das linhas revisadas da ficha.

    Validação obrigatória: por padrão, exige que TODAS as linhas tenham
    CPF + nome + valor + (PIX OU banco completo). Se houver linha com
    essenciais faltantes, devolve 422 com a lista de problemas pra UI
    apontar o que falta.

    Param `forcar=true`: ignora linhas incompletas (descarta) e segue
    com as válidas. Reservado pra admin que sabe o que tá fazendo.

    Após sucesso, a ficha vai pra status CONVERTIDA e fica linkada via
    `lote_gerado_id`. O lote nasce em RECEBIDO e segue o pipeline normal
    (validação → AGUARDANDO_REVISAO → APROVADO → CNAB).
    """
    from app.core.exceptions import ValidacaoError
    from app.models.user import UserRole

    service = FichaService(db)
    ficha = await service.get(ficha_id)
    from app.core.deps import verificar_acesso_cliente

    await verificar_acesso_cliente(db, current_user, ficha.cliente_id)

    # Recalcula essenciais por linha (mesma regra do serializer)
    linhas_raw = ficha.linhas_extraidas or []
    problemas: list[dict] = []
    for idx, l in enumerate(linhas_raw):
        faltam: list[str] = []
        if not (l.get("cpf") or "").strip():
            faltam.append("cpf")
        if not (l.get("nome") or "").strip():
            faltam.append("nome")
        valor = l.get("valor_centavos") or 0
        if not isinstance(valor, int) or valor <= 0:
            faltam.append("valor")
        tem_pix = bool((l.get("chave_pix") or "").strip())
        tem_conta = bool(
            (l.get("banco_codigo") or "").strip()
            and (l.get("agencia") or "").strip()
            and (l.get("conta") or "").strip()
        )
        if not (tem_pix or tem_conta):
            faltam.append("forma_pagamento")
        if faltam:
            problemas.append({
                "linha_index": idx,
                "nome": l.get("nome"),
                "cpf": l.get("cpf"),
                "faltando": faltam,
            })

    if problemas and not forcar:
        # Só admin pode forçar via ?forcar=true
        permite_forcar = current_user.role == UserRole.ADMIN
        raise ValidacaoError(
            f"{len(problemas)} linha(s) com campos essenciais faltando. "
            "Complete os dados na tela de revisão antes de gerar o lote.",
            details={
                "problemas": problemas,
                "total_problemas": len(problemas),
                "pode_forcar": permite_forcar,
            },
        )

    lote = await service.converter_em_lote(
        ficha_id, usuario=current_user, ignorar_incompletas=forcar
    )
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
