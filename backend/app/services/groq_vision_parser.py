"""Parser de fichas via Groq Vision (Llama 4 Scout multimodal).

Em vez de OCR.space + regex sobre texto bruto, este serviço manda a
IMAGEM da ficha direto pro Llama Vision e pede JSON estruturado com
os campos que importam pra um pagamento:

    - CPF (validado)
    - Nome completo
    - Valor em centavos
    - PIX OU (Banco + Agência + Conta)
    - Horas / qtd plantões / especialidade (informativos)

Vantagens vs OCR clássico:
    - Lê QUALQUER layout (tabela, lista, manuscrito misto)
    - Não confunde CPF com chave PIX (entende contexto)
    - Devolve null em vez de inventar quando não conseguiu ler

Quando o Groq falha (rate limit, JSON inválido, chave ausente, etc),
o caller (`ficha._executar_ocr`) cai automaticamente no fluxo antigo
(OCR.space + ficha_parser regex) sem o usuário perceber.

Doc do modelo: https://console.groq.com/docs/vision
"""

from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from app.core.config import settings
from app.core.exceptions import MedPagException
from app.services.ficha_parser import LinhaExtraida, ResultadoParse
from app.validators.cpf import validar_cpf

log = structlog.get_logger()

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqIndisponivelError(MedPagException):
    """GROQ_API_KEY ausente ou Groq fora do ar — caller deve usar fallback."""

    code = "GROQ_INDISPONIVEL"
    status_code = 503


class GroqFalhouError(MedPagException):
    """Groq respondeu mas retorno não é JSON válido ou está vazio."""

    code = "GROQ_FALHOU"
    status_code = 422


@dataclass(frozen=True, slots=True)
class ResultadoVision:
    """Resultado do parser via Groq Vision."""

    parse: ResultadoParse
    modelo: str
    duracao_ms: int
    tokens_entrada: int
    tokens_saida: int
    raw_response: str  # JSON cru retornado (pra debug/auditoria)


# ============================================================
# Prompt — instrução pro modelo
# ============================================================

_SYSTEM_PROMPT = """Você é um leitor especializado em FICHAS DE PLANTÃO MÉDICO brasileiras.

Sua tarefa: olhar a imagem (ou imagens de um PDF) e devolver UM JSON com a lista de médicos que devem ser pagos.

CAMPOS QUE VOCÊ DEVE EXTRAIR DE CADA MÉDICO:
- cpf: string com 11 dígitos (sem pontos/traços). Se aparecer no formato 123.456.789-01, devolva "12345678901". Se não conseguir ler, devolva null.
- nome: nome completo do médico. Preserve "Dr." ou "Dra." se aparecer. Se não conseguir ler, devolva null.
- valor_centavos: valor a pagar em CENTAVOS (inteiro). Ex.: R$ 15.250,00 = 1525000. Se não conseguir ler, devolva null. NÃO INVENTE — null é melhor que chute.
- horas: total de horas trabalhadas (inteiro, sem o "h"). Ex.: "61h" = 61. Se não tiver, null.
- qtd_plantoes: quantidade de plantões (inteiro). Se não aparecer, null.
- especialidade: ex.: "Cirurgião", "Anestesista", "Clínico". Se não aparecer, null.
- banco_codigo: código numérico do banco (3 dígitos, ex.: "237", "001", "341"). Se aparecer "Banco: 33" preencha "033". Se não tiver, null.
- agencia: ex.: "3480", "3480-5". Se não tiver, null.
- conta: número da conta corrente, ex.: "355020-7". Se não tiver, null.
- chave_pix: chave PIX (CPF, email, telefone, EVP). Se for igual ao CPF, repita o CPF aqui também (com pontuação ou sem, qualquer um). Se não tiver, null.

REGRAS CRÍTICAS:
1. NUNCA invente um valor monetário ou um CPF. Se não conseguiu ler com confiança, use null.
2. Se a linha mostra "PIX: <algo>" e separadamente "CPF: <algo diferente>", use o CPF como cpf e o algo do PIX como chave_pix. NÃO MISTURE.
3. Se o pagamento é via PIX, os campos banco_codigo/agencia/conta podem ser null. Se o pagamento é via conta corrente, a chave_pix pode ser null.
4. Ignore linhas de cabeçalho/rodapé (nome do hospital, "PAGAMENTOS:", "Total", "CONFERIDO E APROVADO", "Documento gerado pelo sistema interno", "Plantões pagos: X", etc.). Inclua APENAS médicos com dados de pagamento.
5. Cada médico aparece UMA vez na resposta, mesmo se a ficha repetir.

CABEÇALHO DA FICHA (METADADOS):
Também extraia, se aparecerem:
- hospital: nome do hospital/clínica
- competencia: mês/ano de referência (ex.: "Junho/2026", "06/2026")
- coordenador: nome do coordenador/responsável

FORMATO DA RESPOSTA:
Devolva APENAS um JSON válido (sem ```json, sem texto antes ou depois), exatamente neste shape:

{
  "metadados": {
    "hospital": "string ou null",
    "competencia": "string ou null",
    "coordenador": "string ou null"
  },
  "linhas": [
    {
      "cpf": "12345678901",
      "nome": "Dr. Fulano de Tal",
      "valor_centavos": 1525000,
      "horas": 61,
      "qtd_plantoes": null,
      "especialidade": "Cirurgião",
      "banco_codigo": "237",
      "agencia": "3480",
      "conta": "355020-7",
      "chave_pix": null
    }
  ]
}

Se a imagem não for uma ficha de plantão ou não tiver médicos legíveis, retorne {"metadados": {}, "linhas": []}."""


_USER_PROMPT = """Esta é uma ficha de plantão médico. Extraia a lista de médicos com os campos no formato JSON especificado.
Lembre: null é melhor que inventar. Devolva APENAS o JSON, sem nenhum texto adicional."""


# ============================================================
# Serviço
# ============================================================


class GroqVisionService:
    """Cliente do Groq pra parser de fichas via visão computacional."""

    def __init__(self) -> None:
        self.api_key: str | None = (
            getattr(settings, "GROQ_API_KEY", None) or None
        )
        self.model: str = getattr(
            settings,
            "GROQ_VISION_MODEL",
            "meta-llama/llama-4-scout-17b-16e-instruct",
        )
        self.timeout_s: int = getattr(settings, "GROQ_VISION_TIMEOUT_S", 90)
        self.max_tokens: int = getattr(settings, "GROQ_VISION_MAX_TOKENS", 4096)

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def processar(
        self,
        conteudo: bytes,
        mime_type: str,
        *,
        nome_arquivo: str | None = None,
    ) -> ResultadoVision:
        """Manda a ficha (imagem ou PDF) pro Groq e devolve linhas estruturadas.

        Args:
            conteudo: bytes do arquivo. Pode ser imagem (jpg/png) ou PDF.
            mime_type: tipo do conteúdo (image/jpeg, image/png, application/pdf).
            nome_arquivo: nome original (apenas log).

        Raises:
            GroqIndisponivelError: chave ausente / 503 / timeout / dep faltando
            GroqFalhouError: Groq respondeu mas retorno inválido
        """
        if not self.api_key:
            raise GroqIndisponivelError(
                "GROQ_API_KEY não configurada — usando fallback OCR.space"
            )

        # Se for PDF, converte em uma ou mais imagens PNG antes de enviar.
        # O Llama 4 Scout aceita múltiplas imagens na mesma mensagem.
        if mime_type == "application/pdf" or (
            nome_arquivo and nome_arquivo.lower().endswith(".pdf")
        ):
            try:
                imagens_b64 = _pdf_para_imagens_b64(conteudo)
            except _PdfConversaoError as exc:
                raise GroqIndisponivelError(
                    f"Falha convertendo PDF pra imagem: {exc}"
                ) from exc
            if not imagens_b64:
                raise GroqIndisponivelError("PDF vazio ou sem páginas legíveis")
            data_urls = [
                f"data:image/png;base64,{b64}" for b64 in imagens_b64
            ]
            log.info(
                "groq_vision.pdf_convertido",
                paginas=len(data_urls),
                arquivo=nome_arquivo,
            )
        else:
            # Imagem direta
            b64 = base64.b64encode(conteudo).decode("ascii")
            data_urls = [f"data:{mime_type};base64,{b64}"]

        # Monta conteúdo do user com texto + uma OU MAIS imagens
        user_content: list[dict] = [{"type": "text", "text": _USER_PROMPT}]
        for url in data_urls:
            user_content.append(
                {"type": "image_url", "image_url": {"url": url}}
            )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        log.info(
            "groq_vision.enviando",
            modelo=self.model,
            tamanho_kb=round(len(conteudo) / 1024, 1),
            mime=mime_type,
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise GroqIndisponivelError(
                f"Timeout no Groq após {self.timeout_s}s — usando fallback"
            ) from exc
        except httpx.HTTPError as exc:
            raise GroqIndisponivelError(
                f"Falha de rede com Groq: {exc}"
            ) from exc

        if response.status_code == 401:
            raise GroqIndisponivelError(
                "GROQ_API_KEY inválida — verifique em console.groq.com/keys"
            )
        if response.status_code == 429:
            raise GroqIndisponivelError(
                "Cota do Groq esgotada (rate limit) — usando fallback"
            )
        if response.status_code >= 400:
            log.warning(
                "groq_vision.http_status",
                status=response.status_code,
                body=response.text[:500],
            )
            raise GroqIndisponivelError(
                f"Groq respondeu HTTP {response.status_code}"
            )

        try:
            payload_resp = response.json()
        except ValueError as exc:
            raise GroqFalhouError(
                "Groq respondeu com payload não-JSON"
            ) from exc

        choices = payload_resp.get("choices") or []
        if not choices:
            raise GroqFalhouError("Groq devolveu choices vazio")

        raw_content = (
            choices[0].get("message", {}).get("content") or ""
        ).strip()
        usage = payload_resp.get("usage", {}) or {}
        tokens_in = int(usage.get("prompt_tokens") or 0)
        tokens_out = int(usage.get("completion_tokens") or 0)

        # Parsing do JSON devolvido pelo modelo
        parsed = _extrair_json(raw_content)
        if parsed is None:
            log.warning(
                "groq_vision.json_invalido",
                raw_preview=raw_content[:300],
            )
            raise GroqFalhouError(
                "Groq não devolveu JSON válido — caindo no fallback"
            )

        # Converte pro ResultadoParse padrão (mesmo shape do regex parser)
        linhas = _normalizar_linhas(parsed.get("linhas") or [])
        metadados = _normalizar_metadados(parsed.get("metadados") or {})

        log.info(
            "groq_vision.concluido",
            modelo=self.model,
            linhas=len(linhas),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

        return ResultadoVision(
            parse=ResultadoParse(linhas=linhas, metadados=metadados),
            modelo=self.model,
            duracao_ms=0,  # Groq devolve total_time no payload mas vem em segundos
            tokens_entrada=tokens_in,
            tokens_saida=tokens_out,
            raw_response=raw_content,
        )


# ============================================================
# Helpers — conversão PDF -> imagem
# ============================================================


class _PdfConversaoError(Exception):
    """Erro convertendo PDF em imagem (lib ausente, PDF corrompido, etc)."""


# Resolução de renderização do PDF — 150 DPI é ótimo equilíbrio entre
# legibilidade e tamanho (1 página A4 vira ~250-500 KB de PNG).
_PDF_RENDER_SCALE = 150 / 72  # 150 DPI (PDF default é 72 DPI)
# Máximo de páginas que mandamos pro Groq de uma vez. Acima disso, fica
# caro/lento e o modelo pode perder contexto.
_PDF_MAX_PAGINAS = 6


def _pdf_para_imagens_b64(conteudo_pdf: bytes) -> list[str]:
    """Converte cada página do PDF em PNG base64.

    Usa pypdfium2 (pure-python wheel, sem dependência de poppler).
    Retorna lista de strings base64 — uma por página, na ordem.

    Raises:
        _PdfConversaoError: se a lib não estiver disponível ou o PDF
            estiver corrompido / vazio.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise _PdfConversaoError(
            "pypdfium2 não está instalado — adicione ao requirements.txt"
        ) from exc

    try:
        pdf = pdfium.PdfDocument(conteudo_pdf)
    except Exception as exc:
        raise _PdfConversaoError(
            f"PDF corrompido ou ilegível: {exc}"
        ) from exc

    imagens_b64: list[str] = []
    total = min(len(pdf), _PDF_MAX_PAGINAS)
    for i in range(total):
        try:
            page = pdf[i]
            pil_image = page.render(scale=_PDF_RENDER_SCALE).to_pil()
            buf = io.BytesIO()
            pil_image.save(buf, format="PNG", optimize=True)
            imagens_b64.append(base64.b64encode(buf.getvalue()).decode("ascii"))
        except Exception as exc:
            log.warning(
                "groq_vision.pagina_falhou", pagina=i + 1, erro=str(exc)
            )
            continue
    pdf.close()
    return imagens_b64


# ============================================================
# Helpers de parsing/normalização
# ============================================================


def _extrair_json(texto: str) -> dict[str, Any] | None:
    """Extrai JSON do retorno do modelo.

    Llama às vezes enrola num ```json ... ``` mesmo com response_format
    setado. Aceitamos as 2 formas.
    """
    s = texto.strip()
    if not s:
        return None

    # Remove cercas de código se vieram
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s)

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # Última tentativa: pega o primeiro objeto JSON encontrado
        match = re.search(r"\{[\s\S]*\}", s)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return None


def _normalizar_linhas(linhas_raw: list[Any]) -> list[LinhaExtraida]:
    """Valida e normaliza cada linha pro shape interno."""
    resultado: list[LinhaExtraida] = []
    for item in linhas_raw:
        if not isinstance(item, dict):
            continue

        # CPF
        cpf_bruto = _str_ou_none(item.get("cpf"))
        cpf_limpo: str | None = None
        avisos: list[str] = []
        if cpf_bruto:
            res = validar_cpf(cpf_bruto)
            if res.cpf_limpo and len(res.cpf_limpo) == 11:
                cpf_limpo = res.cpf_limpo
                if not res.is_valido:
                    avisos.append(f"CPF inválido: {res.mensagem}")

        # Valor
        valor_centavos = _int_positivo(item.get("valor_centavos"))

        # Linha
        linha = LinhaExtraida(
            cpf=cpf_limpo,
            nome=_str_ou_none(item.get("nome")),
            valor_centavos=valor_centavos,
            qtd_plantoes=_int_positivo(item.get("qtd_plantoes")),
            horas=_int_positivo(item.get("horas")),
            especialidade=_str_ou_none(item.get("especialidade")),
            banco_codigo=_normalizar_banco(item.get("banco_codigo")),
            agencia=_str_ou_none(item.get("agencia")),
            conta=_str_ou_none(item.get("conta")),
            chave_pix=_str_ou_none(item.get("chave_pix")),
            linha_origem="[groq-vision]",
            avisos=avisos,
        )
        resultado.append(linha)
    return resultado


def _normalizar_metadados(meta_raw: dict[str, Any]) -> dict[str, Any]:
    return {
        chave: valor.strip() if isinstance(valor, str) and valor.strip() else None
        for chave, valor in meta_raw.items()
        if chave in ("hospital", "competencia", "coordenador")
    }


def _str_ou_none(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("null", "none", "n/a", "-", ""):
        return None
    return s


def _int_positivo(v: Any) -> int | None:
    if v is None:
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        try:
            n = int(float(v))
        except (TypeError, ValueError):
            return None
    return n if n > 0 else None


def _normalizar_banco(v: Any) -> str | None:
    s = _str_ou_none(v)
    if not s:
        return None
    digitos = re.sub(r"\D", "", s)
    if not digitos:
        return None
    return digitos.zfill(3)[:3]


# Singleton
groq_vision_service = GroqVisionService()


__all__ = [
    "GroqFalhouError",
    "GroqIndisponivelError",
    "GroqVisionService",
    "ResultadoVision",
    "groq_vision_service",
]
