"""Exceções de domínio do MedPag.

Toda exceção de negócio deve herdar de `MedPagException`. O handler
global em `app/main.py` traduz isso para resposta JSON estruturada
com `code`, `message` e `success: False`.

NUNCA levante `Exception` ou `ValueError` direto numa rota — sempre
use uma das exceções desta hierarquia.
"""

from __future__ import annotations

from typing import Any


class MedPagException(Exception):
    """Exceção base do domínio MedPag.

    Atributos:
        code: Código identificador (ex: `LOTE_JA_PROCESSADO`)
        message: Mensagem em português acionável
        status_code: HTTP status code que será retornado
        details: Detalhes adicionais (vão pro JSON da resposta)
    """

    code: str = "ERRO_INTERNO"
    status_code: int = 400

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serializa para JSON conforme padrão da API."""
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            payload.update(self.details)
        return payload


# ============================================================
# Exceções de Lote
# ============================================================


class LoteJaProcessadoError(MedPagException):
    """Hash do lote já existe — idempotência impede duplicação."""

    code = "LOTE_JA_PROCESSADO"
    status_code = 409  # Conflict


class LoteNaoEncontradoError(MedPagException):
    code = "LOTE_NAO_ENCONTRADO"
    status_code = 404


class LoteNaoAprovavelError(MedPagException):
    """Tentou aprovar um lote em status que não permite aprovação."""

    code = "LOTE_NAO_APROVAVEL"
    status_code = 409


class LoteFormatoNaoReconhecidoError(MedPagException):
    """Não conseguiu mapear as colunas da planilha."""

    code = "LOTE_FORMATO_NAO_RECONHECIDO"
    status_code = 422


class LoteVazioError(MedPagException):
    code = "LOTE_VAZIO"
    status_code = 422


# ============================================================
# Exceções de Pagamento
# ============================================================


class PagamentoNaoEncontradoError(MedPagException):
    code = "PAGAMENTO_NAO_ENCONTRADO"
    status_code = 404


class PagamentoNaoEditavelError(MedPagException):
    """Pagamento já aprovado/enviado não pode ser editado."""

    code = "PAGAMENTO_NAO_EDITAVEL"
    status_code = 409


# ============================================================
# Exceções de Autenticação / Autorização
# ============================================================


class CredenciaisInvalidasError(MedPagException):
    code = "CREDENCIAIS_INVALIDAS"
    status_code = 401


class TokenInvalidoError(MedPagException):
    code = "TOKEN_INVALIDO"
    status_code = 401


class TokenExpiradoError(MedPagException):
    code = "TOKEN_EXPIRADO"
    status_code = 401


class PermissaoNegadaError(MedPagException):
    """Usuário autenticado sem permissão para esta operação."""

    code = "PERMISSAO_NEGADA"
    status_code = 403


class UsuarioInativoError(MedPagException):
    code = "USUARIO_INATIVO"
    status_code = 403


# ============================================================
# Exceções de Usuário (gestão admin)
# ============================================================


class UsuarioJaExisteError(MedPagException):
    """E-mail já cadastrado no sistema."""

    code = "USUARIO_JA_EXISTE"
    status_code = 409


class UsuarioNaoEncontradoError(MedPagException):
    code = "USUARIO_NAO_ENCONTRADO"
    status_code = 404


# ============================================================
# Exceções de Configuração
# ============================================================


class EmpresaConfigNaoEncontradaError(MedPagException):
    """Não há EmpresaConfig ativa — sistema não pode gerar CNAB."""

    code = "EMPRESA_CONFIG_NAO_ENCONTRADA"
    status_code = 412  # Precondition Failed


# ============================================================
# Exceções de Validação genéricas
# ============================================================


class ValidacaoError(MedPagException):
    code = "VALIDACAO_ERRO"
    status_code = 422


__all__ = [
    "CredenciaisInvalidasError",
    "EmpresaConfigNaoEncontradaError",
    "LoteFormatoNaoReconhecidoError",
    "LoteJaProcessadoError",
    "LoteNaoAprovavelError",
    "LoteNaoEncontradoError",
    "LoteVazioError",
    "MedPagException",
    "PagamentoNaoEditavelError",
    "PagamentoNaoEncontradoError",
    "PermissaoNegadaError",
    "TokenExpiradoError",
    "TokenInvalidoError",
    "UsuarioInativoError",
    "UsuarioJaExisteError",
    "UsuarioNaoEncontradoError",
    "ValidacaoError",
]
