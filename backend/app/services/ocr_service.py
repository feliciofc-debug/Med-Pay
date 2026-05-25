"""Integração com OCR.space para extração de texto em fichas escaneadas.

OCR.space oferece 25.000 páginas/mês gratuitas com `OCREngine=2`, que é
o mais preciso para documentos manuscritos/carimbados (caso típico das
fichas de plantão que coordenadores enviam).

Documentação: https://ocr.space/ocrapi
Limite plano free: 5MB por arquivo / 3 páginas por PDF / 25k páginas/mês.

A chave da API vem da variável `OCR_SPACE_API_KEY` (settings). Se ela
não estiver configurada, `is_available()` retorna False e o uso de
OCR é bloqueado com mensagem amigável — sem quebrar o startup.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

from app.core.config import settings
from app.core.exceptions import MedPagException

log = structlog.get_logger()

OCR_SPACE_URL = "https://api.ocr.space/parse/image"
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB (limite do plano gratuito)
HTTP_TIMEOUT_SECONDS = 120  # PDFs grandes podem levar até 2 min

_MIME_TYPES_IMAGEM: dict[str, str] = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "tiff": "image/tiff",
    "tif": "image/tiff",
    "bmp": "image/bmp",
    "webp": "image/webp",
}


class OCRIndisponivelError(MedPagException):
    """OCR_SPACE_API_KEY ausente ou serviço fora do ar."""

    code = "OCR_INDISPONIVEL"
    status_code = 503


class OCRFalhouError(MedPagException):
    """OCR retornou erro (arquivo corrompido, ilegível, limite atingido)."""

    code = "OCR_FALHOU"
    status_code = 422


@dataclass(frozen=True, slots=True)
class ResultadoOCR:
    """Resultado da extração OCR."""

    texto: str
    paginas: int
    duracao_ms: int


class OCRService:
    """Cliente do OCR.space.

    Use `processar_pdf` para PDFs escaneados e `processar_imagem` para
    fotos da ficha (JPG/PNG/TIFF). O serviço já vem configurado para
    português (`language=por`) e Engine 2 (melhor para tabelas e carimbos).
    """

    def __init__(self) -> None:
        self.api_key: str | None = getattr(settings, "OCR_SPACE_API_KEY", None) or None
        if not self.api_key:
            log.warning(
                "ocr.api_key_missing",
                msg="OCR_SPACE_API_KEY não configurada — extração via OCR indisponível",
            )

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def processar_pdf(
        self, conteudo: bytes, nome_arquivo: str, *, e_tabela: bool = True
    ) -> ResultadoOCR:
        """Extrai texto de um PDF (escaneado ou nativo).

        Args:
            conteudo: bytes do PDF
            nome_arquivo: nome original (apenas informativo nos logs)
            e_tabela: True habilita o parser de tabelas (recomendado para
                fichas com linhas/colunas de plantões)
        """
        return await self._processar(
            conteudo=conteudo,
            nome_arquivo=nome_arquivo,
            mime_type="application/pdf",
            extras={"isTable": "true" if e_tabela else "false", "filetype": "PDF"},
        )

    async def processar_imagem(
        self, conteudo: bytes, nome_arquivo: str
    ) -> ResultadoOCR:
        """Extrai texto de uma imagem (foto da ficha)."""
        ext = nome_arquivo.lower().rsplit(".", 1)[-1] if "." in nome_arquivo else ""
        mime = _MIME_TYPES_IMAGEM.get(ext, "image/png")
        return await self._processar(
            conteudo=conteudo, nome_arquivo=nome_arquivo, mime_type=mime, extras={}
        )

    async def _processar(
        self,
        *,
        conteudo: bytes,
        nome_arquivo: str,
        mime_type: str,
        extras: dict[str, str],
    ) -> ResultadoOCR:
        if not self.api_key:
            raise OCRIndisponivelError(
                "OCR não disponível: defina OCR_SPACE_API_KEY no servidor "
                "(https://ocr.space/ocrapi para chave gratuita)."
            )

        if len(conteudo) > MAX_FILE_SIZE_BYTES:
            log.warning(
                "ocr.arquivo_grande",
                arquivo=nome_arquivo,
                tamanho_mb=round(len(conteudo) / 1024 / 1024, 2),
            )
            # OCR.space rejeita > 1MB no plano free com PRO endpoint;
            # com a chave free comum aceita até ~5MB. Tentamos mesmo assim.

        files = {
            "file": (nome_arquivo, conteudo, mime_type),
        }
        data = {
            "apikey": self.api_key,
            "language": "por",
            "isOverlayRequired": "false",
            "detectOrientation": "true",
            "scale": "true",
            "OCREngine": "2",
            **extras,
        }

        log.info(
            "ocr.enviando",
            arquivo=nome_arquivo,
            tamanho_kb=round(len(conteudo) / 1024, 1),
            mime=mime_type,
        )

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
                response = await client.post(OCR_SPACE_URL, files=files, data=data)
        except httpx.TimeoutException as exc:
            raise OCRFalhouError(
                "Timeout no OCR — documento muito grande ou conexão lenta. "
                "Tente reduzir a resolução da imagem."
            ) from exc
        except httpx.HTTPError as exc:
            log.error("ocr.http_error", erro=str(exc))
            raise OCRFalhouError(
                f"Falha de comunicação com OCR.space: {exc}"
            ) from exc

        if response.status_code == 403:
            raise OCRIndisponivelError(
                "Chave OCR.space inválida ou cota mensal esgotada (25k páginas)."
            )

        if response.status_code >= 400:
            log.error(
                "ocr.http_status",
                status=response.status_code,
                body=response.text[:500],
            )
            raise OCRFalhouError(
                f"OCR.space respondeu HTTP {response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise OCRFalhouError("OCR.space respondeu com payload inválido") from exc

        if payload.get("IsErroredOnProcessing") or payload.get("OCRExitCode") not in (
            1,
            2,
        ):
            erros = payload.get("ErrorMessage") or ["erro desconhecido"]
            mensagem = "; ".join(str(e) for e in erros if e)
            raise OCRFalhouError(f"OCR falhou: {mensagem}")

        textos: list[str] = []
        for resultado in payload.get("ParsedResults") or []:
            if resultado.get("FileParseExitCode") == 1:
                texto = resultado.get("ParsedText") or ""
                if texto.strip():
                    textos.append(texto)
            elif resultado.get("ErrorMessage"):
                log.warning("ocr.pagina_com_erro", erro=resultado["ErrorMessage"])

        texto_final = "\n\n".join(textos)
        paginas = len(payload.get("ParsedResults") or [])

        # ProcessingTimeInMilliseconds vem como string em algumas respostas
        try:
            duracao_ms = int(payload.get("ProcessingTimeInMilliseconds") or 0)
        except (TypeError, ValueError):
            duracao_ms = 0

        log.info(
            "ocr.concluido",
            arquivo=nome_arquivo,
            paginas=paginas,
            chars=len(texto_final),
            duracao_ms=duracao_ms,
        )

        return ResultadoOCR(texto=texto_final, paginas=paginas, duracao_ms=duracao_ms)


# Singleton — uma instância por processo. A chave é lida no construtor.
ocr_service = OCRService()


__all__ = [
    "OCRFalhouError",
    "OCRIndisponivelError",
    "OCRService",
    "ResultadoOCR",
    "ocr_service",
]
