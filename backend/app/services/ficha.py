"""Service de FichaPlantao — orquestra upload, OCR, parser e conversão em lote.

Fluxo completo:

    upload bytes
        → calcula hash, checa duplicata
        → grava registro com status RECEBIDA
        → chama OCR (PROCESSANDO → EXTRAIDA / ERRO)
        → parser estrutura linhas
        → aprovador edita na UI (REVISADA)
        → converte em Lote (CONVERTIDA + lote_gerado_id)

A conversão em lote reaproveita o pipeline de planilha: monta um
`ResultadoImportacao` em memória a partir das linhas revisadas, e
chama o `LoteService.criar_a_partir_de_linhas` (atalho que evita
serializar/deserializar XLSX).
"""

from __future__ import annotations

import hashlib
import io
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pandas as pd
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import MedPagException, ValidacaoError
from app.models.cliente import Cliente
from app.models.ficha_plantao import FichaPlantao, StatusFicha
from app.models.lote import Lote
from app.models.user import User
from app.services.ficha_parser import parsear_ficha
from app.services.groq_vision_parser import (
    GroqFalhouError,
    GroqIndisponivelError,
    groq_vision_service,
)
from app.services.ocr_service import OCRFalhouError, OCRIndisponivelError, ocr_service

log = structlog.get_logger()

EXTENSOES_IMAGEM = {"jpg", "jpeg", "png", "tiff", "tif", "bmp", "webp"}
EXTENSOES_PDF = {"pdf"}
EXTENSOES_SUPORTADAS = EXTENSOES_IMAGEM | EXTENSOES_PDF


class FichaNaoEncontradaError(MedPagException):
    code = "FICHA_NAO_ENCONTRADA"
    status_code = 404


class FichaJaProcessadaError(MedPagException):
    code = "FICHA_JA_PROCESSADA"
    status_code = 409


class FichaNaoConvertivelError(MedPagException):
    code = "FICHA_NAO_CONVERTIVEL"
    status_code = 409


class FichaService:
    """Orquestra ciclo de vida de FichaPlantao."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ============================================================
    # Upload + OCR
    # ============================================================

    async def criar_a_partir_de_upload(
        self,
        *,
        conteudo: bytes,
        nome_arquivo: str,
        mime_type: str,
        cliente: Cliente,
        enviado_por: User | None = None,
        executar_ocr: bool = True,
    ) -> FichaPlantao:
        """Recebe arquivo da ficha, persiste e (opcional) roda OCR síncrono.

        Para arquivos pequenos (até ~3MB), o OCR síncrono é OK — leva 5-15s.
        Para arquivos maiores, mover para worker em fila no futuro.
        """
        if not conteudo:
            raise ValidacaoError("Arquivo vazio")

        ext = nome_arquivo.lower().rsplit(".", 1)[-1] if "." in nome_arquivo else ""
        if ext not in EXTENSOES_SUPORTADAS:
            raise ValidacaoError(
                f"Formato '{ext}' não suportado. "
                f"Use: {', '.join(sorted(EXTENSOES_SUPORTADAS))}."
            )

        hash_arquivo = hashlib.sha256(conteudo).hexdigest()

        # Idempotência: mesmo hash → reusa a ficha já criada
        existente_q = await self.db.execute(
            select(FichaPlantao).where(FichaPlantao.hash_arquivo == hash_arquivo)
        )
        existente = existente_q.scalar_one_or_none()
        if existente is not None:
            raise FichaJaProcessadaError(
                f"Esta ficha já foi enviada em "
                f"{existente.created_at.strftime('%d/%m/%Y %H:%M')}",
                details={"ficha_id": str(existente.id)},
            )

        ficha = FichaPlantao(
            cliente_id=cliente.id,
            nome_arquivo=nome_arquivo,
            mime_type=mime_type,
            tamanho_bytes=len(conteudo),
            arquivo_bytes=conteudo,
            hash_arquivo=hash_arquivo,
            status=StatusFicha.RECEBIDA,
            enviado_por_id=enviado_por.id if enviado_por else None,
        )
        self.db.add(ficha)
        await self.db.flush()

        log.info(
            "ficha.criada",
            ficha_id=str(ficha.id),
            cliente_id=str(cliente.id),
            tamanho_kb=round(len(conteudo) / 1024, 1),
            extensao=ext,
        )

        if executar_ocr:
            await self._executar_ocr(ficha, ext)

        return ficha

    async def _executar_ocr(self, ficha: FichaPlantao, ext: str) -> None:
        """Roda OCR + parser e atualiza a ficha.

        Pipeline híbrido (em ordem de prioridade):
            1. Groq Vision (Llama 4 Scout) — lê IMAGEM direto, devolve JSON.
               Funciona em qualquer layout, qualquer hospital. Free tier
               do Groq tem ~14k requisições/dia, sobra.
            2. Se Groq falhar (chave ausente, rate limit, timeout, JSON
               inválido, etc), cai automaticamente em OCR.space + regex.
            3. Se OCR.space também falhar, marca ficha como ERRO.

        Em ambos os casos o `linhas_extraidas` sai no mesmo formato
        (`LinhaExtraida.to_dict()`) — frontend não precisa saber qual
        caminho foi usado.
        """
        from app.core.config import settings

        ficha.status = StatusFicha.PROCESSANDO
        await self.db.flush()

        provider_usado: str | None = None
        try:
            parse = None
            texto_bruto: str | None = None
            paginas_ocr = 0

            # =========== TENTATIVA 1: Groq Vision ===========
            # Aceita IMAGEM (jpg/png) e PDF (convertido em PNG por página
            # via pypdfium2 dentro do groq_vision_service).
            usar_groq = getattr(
                settings, "USAR_GROQ_VISION", True
            ) and groq_vision_service.is_available()
            if usar_groq:
                try:
                    mime = ficha.mime_type or (
                        "application/pdf" if ext in EXTENSOES_PDF else "image/jpeg"
                    )
                    resultado_vision = await groq_vision_service.processar(
                        ficha.arquivo_bytes,
                        mime,
                        nome_arquivo=ficha.nome_arquivo,
                    )
                    parse = resultado_vision.parse
                    texto_bruto = resultado_vision.raw_response
                    paginas_ocr = 1
                    provider_usado = "groq-vision"
                    log.info(
                        "ficha.groq_vision_ok",
                        ficha_id=str(ficha.id),
                        linhas=len(parse.linhas),
                        modelo=resultado_vision.modelo,
                        tokens_in=resultado_vision.tokens_entrada,
                        tokens_out=resultado_vision.tokens_saida,
                    )
                except (GroqIndisponivelError, GroqFalhouError) as exc:
                    log.info(
                        "ficha.groq_vision_fallback",
                        ficha_id=str(ficha.id),
                        motivo=exc.message,
                    )

            # =========== TENTATIVA 2: OCR.space + regex parser ===========
            if parse is None:
                if ext in EXTENSOES_PDF:
                    resultado = await ocr_service.processar_pdf(
                        ficha.arquivo_bytes, ficha.nome_arquivo
                    )
                else:
                    resultado = await ocr_service.processar_imagem(
                        ficha.arquivo_bytes, ficha.nome_arquivo
                    )
                parse = parsear_ficha(resultado.texto)
                texto_bruto = resultado.texto
                paginas_ocr = resultado.paginas
                provider_usado = "ocr-space"

            ficha.texto_ocr = texto_bruto
            ficha.paginas_ocr = paginas_ocr
            ficha.linhas_extraidas = [linha.to_dict() for linha in parse.linhas]
            # Anota qual provider gerou — útil pra debug e auditoria
            metadados_final = dict(parse.metadados or {})
            metadados_final["_provider"] = provider_usado
            ficha.metadados = metadados_final
            ficha.status = StatusFicha.EXTRAIDA
            ficha.mensagem_erro = None

            log.info(
                "ficha.ocr_concluido",
                ficha_id=str(ficha.id),
                provider=provider_usado,
                linhas=len(parse.linhas),
                paginas=paginas_ocr,
            )

        except (OCRIndisponivelError, OCRFalhouError) as exc:
            ficha.status = StatusFicha.ERRO
            ficha.mensagem_erro = exc.message
            log.warning(
                "ficha.ocr_falhou", ficha_id=str(ficha.id), erro=exc.message
            )
        except Exception as exc:  # pragma: no cover — guard de robustez
            ficha.status = StatusFicha.ERRO
            ficha.mensagem_erro = f"Erro inesperado no OCR: {type(exc).__name__}: {exc}"
            log.exception("ficha.ocr_excecao", ficha_id=str(ficha.id))

        await self.db.flush()

    # ============================================================
    # Recuperação / listagem
    # ============================================================

    async def get(self, ficha_id: UUID) -> FichaPlantao:
        result = await self.db.execute(
            select(FichaPlantao)
            .where(FichaPlantao.id == ficha_id)
            .options(selectinload(FichaPlantao.cliente))
        )
        ficha = result.scalar_one_or_none()
        if ficha is None:
            raise FichaNaoEncontradaError(f"Ficha {ficha_id} não encontrada")
        return ficha

    async def listar(
        self,
        *,
        status: StatusFicha | None = None,
        cliente_id: UUID | None = None,
        enviado_por_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FichaPlantao]:
        query = (
            select(FichaPlantao)
            .options(selectinload(FichaPlantao.cliente))
            .order_by(FichaPlantao.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            query = query.where(FichaPlantao.status == status)
        if cliente_id is not None:
            query = query.where(FichaPlantao.cliente_id == cliente_id)
        if enviado_por_id is not None:
            query = query.where(FichaPlantao.enviado_por_id == enviado_por_id)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ============================================================
    # Edição manual das linhas extraídas
    # ============================================================

    async def atualizar_linhas(
        self,
        ficha_id: UUID,
        *,
        linhas: list[dict[str, Any]],
        metadados: dict[str, Any] | None,
        revisor: User,
    ) -> FichaPlantao:
        """Substitui as linhas extraídas pelas que o revisor enviou."""
        ficha = await self.get(ficha_id)

        if ficha.status == StatusFicha.CONVERTIDA:
            raise FichaNaoConvertivelError(
                "Ficha já foi convertida em lote — não pode ser editada"
            )

        # Limpeza mínima dos campos
        linhas_limpas: list[dict[str, Any]] = []
        for raw in linhas:
            if not isinstance(raw, dict):
                continue
            linhas_limpas.append(
                {
                    "cpf": _str_ou_none(raw.get("cpf")),
                    "nome": _str_ou_none(raw.get("nome")),
                    "valor_centavos": _int_ou_none(raw.get("valor_centavos")),
                    "qtd_plantoes": _int_ou_none(raw.get("qtd_plantoes")),
                    "horas": _int_ou_none(raw.get("horas")),
                    "banco_codigo": _str_ou_none(raw.get("banco_codigo")),
                    "agencia": _str_ou_none(raw.get("agencia")),
                    "conta": _str_ou_none(raw.get("conta")),
                    "chave_pix": _str_ou_none(raw.get("chave_pix")),
                    "linha_origem": _str_ou_none(raw.get("linha_origem")) or "",
                    "avisos": list(raw.get("avisos") or []),
                }
            )

        ficha.linhas_extraidas = linhas_limpas
        ficha.metadados = metadados or ficha.metadados
        ficha.status = StatusFicha.REVISADA
        ficha.revisado_por_id = revisor.id
        ficha.revisado_at = datetime.now(UTC)

        await self.db.flush()

        log.info(
            "ficha.revisada",
            ficha_id=str(ficha.id),
            linhas=len(linhas_limpas),
            revisor_id=str(revisor.id),
        )

        return ficha

    async def reexecutar_ocr(self, ficha_id: UUID) -> FichaPlantao:
        """Reprocessa o OCR (útil quando a chave foi adicionada após upload)."""
        ficha = await self.get(ficha_id)
        if ficha.status == StatusFicha.CONVERTIDA:
            raise FichaNaoConvertivelError(
                "Ficha já virou lote, OCR não pode ser refeito"
            )
        ext = (
            ficha.nome_arquivo.lower().rsplit(".", 1)[-1]
            if "." in ficha.nome_arquivo
            else ""
        )
        await self._executar_ocr(ficha, ext)
        return ficha

    # ============================================================
    # Conversão em lote
    # ============================================================

    async def converter_em_lote(
        self,
        ficha_id: UUID,
        *,
        usuario: User,
        ignorar_incompletas: bool = False,
    ) -> Lote:
        """Gera um XLSX em memória a partir das linhas revisadas e
        cria um lote pelo pipeline normal (`LoteService`).

        Reaproveitamos o caminho de planilha pra não duplicar lógica
        de validação/criação de pagamentos. A ficha vira "fonte" e fica
        registrada via `lote.referencia` + `ficha.lote_gerado_id`.
        """
        # Import local pra evitar ciclo (lote → auditoria → ... → ficha)
        from app.services.lote import LoteService

        ficha = await self.get(ficha_id)

        if ficha.status not in (StatusFicha.EXTRAIDA, StatusFicha.REVISADA):
            raise FichaNaoConvertivelError(
                f"Ficha em status {ficha.status.value} não pode virar lote. "
                "Revise as linhas extraídas antes."
            )

        linhas = ficha.linhas_extraidas or []
        if not linhas:
            raise FichaNaoConvertivelError(
                "Ficha sem linhas extraídas — nada para enviar"
            )

        linhas_validas = [
            linha
            for linha in linhas
            if linha.get("cpf") and linha.get("nome") and linha.get("valor_centavos")
        ]
        if not linhas_validas:
            raise FichaNaoConvertivelError(
                "Nenhuma linha tem CPF + nome + valor preenchidos. "
                "Complete os dados na revisão antes de gerar o lote."
            )

        xlsx_bytes = _linhas_para_xlsx(linhas_validas)
        nome_xlsx = f"ficha-{ficha.id.hex[:8]}.xlsx"

        lote_service = LoteService(self.db)
        lote, importacao = await lote_service.criar_a_partir_de_upload(
            conteudo=xlsx_bytes,
            nome_arquivo=nome_xlsx,
            cliente=ficha.cliente,
            enviado_por=usuario,
        )

        # Marca origem
        meta = ficha.metadados or {}
        if competencia := meta.get("competencia"):
            lote.referencia = f"Ficha {competencia}"
        else:
            lote.referencia = f"Ficha {ficha.created_at.strftime('%m/%Y')}"

        ficha.lote_gerado_id = lote.id
        ficha.status = StatusFicha.CONVERTIDA
        if ficha.revisado_por_id is None:
            ficha.revisado_por_id = usuario.id
            ficha.revisado_at = datetime.now(UTC)

        await self.db.flush()

        # Dispara processamento síncrono (cria os Pagamentos).
        # Sem isso, o lote ficava em RECEBIDO sem pagamento nenhum
        # e o admin precisava reprocessar manualmente.
        # Paridade com /api/lotes/upload (que enfileira via Celery ou
        # roda fallback inline) — aqui vamos sempre inline porque a
        # ficha tem volume baixo (1-2 páginas, ~30 linhas).
        from app.services.processamento import processar_lote

        try:
            await processar_lote(self.db, lote, importacao.linhas)
            await self.db.flush()
        except Exception:  # noqa: BLE001
            # Mantém lote em RECEBIDO pra reprocessar manualmente.
            log.exception(
                "ficha.processar_lote_falhou",
                ficha_id=str(ficha.id),
                lote_id=str(lote.id),
            )

        log.info(
            "ficha.convertida_em_lote",
            ficha_id=str(ficha.id),
            lote_id=str(lote.id),
            qtd_linhas=len(linhas_validas),
            lote_status=lote.status.value,
        )

        return lote

    async def deletar(self, ficha_id: UUID) -> None:
        ficha = await self.get(ficha_id)
        if ficha.status == StatusFicha.CONVERTIDA:
            raise FichaNaoConvertivelError(
                "Não é possível deletar uma ficha que já virou lote "
                "(quebraria o histórico). Delete o lote primeiro."
            )
        await self.db.delete(ficha)
        await self.db.flush()


# ============================================================
# Helpers
# ============================================================


def _str_ou_none(valor: Any) -> str | None:
    if valor is None:
        return None
    s = str(valor).strip()
    return s or None


def _int_ou_none(valor: Any) -> int | None:
    if valor is None or valor == "":
        return None
    try:
        return int(valor)
    except (ValueError, TypeError):
        return None


def _linhas_para_xlsx(linhas: list[dict[str, Any]]) -> bytes:
    """Gera um XLSX em memória com colunas no padrão do importador.

    Layout — colunas que o `importacao.py` reconhece automaticamente:
        CPF | Nome | Banco | Agência | Conta | Valor | Chave PIX

    A coluna "Chave PIX" aciona modalidade PIX no `_decidir_modalidade`
    e dispensa banco/ag/conta na validação. Usado pra pagamentos que
    vieram da ficha já com PIX preenchido (Felipe / Rafael na Santa Casa).

    Valor sai em reais com vírgula (formato BR) pra preservar o que o
    parser/heurística de importação espera.
    """
    rows: list[dict[str, str]] = []
    for linha in linhas:
        valor_centavos = int(linha.get("valor_centavos") or 0)
        valor_reais = valor_centavos / 100
        valor_str = f"{valor_reais:.2f}".replace(".", ",")
        rows.append(
            {
                "CPF": str(linha.get("cpf") or ""),
                "Nome": str(linha.get("nome") or ""),
                "Banco": str(linha.get("banco_codigo") or ""),
                "Agência": str(linha.get("agencia") or ""),
                "Conta": str(linha.get("conta") or ""),
                "Valor": valor_str,
                "Chave PIX": str(linha.get("chave_pix") or ""),
            }
        )

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Fichas")
    return buf.getvalue()


__all__ = [
    "FichaJaProcessadaError",
    "FichaNaoConvertivelError",
    "FichaNaoEncontradaError",
    "FichaService",
]
