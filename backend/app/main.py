"""Entrypoint da API FastAPI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import MedPagException

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle da aplicação (startup/shutdown)."""
    log.info("medpag.startup", environment=settings.ENVIRONMENT, version="0.1.0")
    yield
    log.info("medpag.shutdown")


def _configure_logging() -> None:
    """Configura structlog para JSON em produção, console-friendly em dev."""
    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    if settings.is_production:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
        cache_logger_on_first_use=True,
    )


def _register_exception_handlers(app: FastAPI) -> None:
    """Handlers globais — toda exceção vira JSON estruturado."""

    @app.exception_handler(MedPagException)
    async def medpag_exception_handler(
        request: Request, exc: MedPagException
    ) -> JSONResponse:
        log.warning(
            "medpag.business_error",
            code=exc.code,
            message=exc.message,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": exc.to_dict()},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = []
        for err in exc.errors():
            loc = err.get("loc", [])
            field = ".".join(str(item) for item in loc[1:]) if len(loc) > 1 else "body"
            errors.append(
                {
                    "field": field,
                    "code": err.get("type", "VALIDACAO_ERRO").upper(),
                    "message": err.get("msg", "Valor inválido"),
                }
            )
        return JSONResponse(
            status_code=422,
            content={"success": False, "errors": errors},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        # Pega QUALQUER exception não tratada e devolve JSON com CORS aplicado
        # (caso contrário, browser bloqueia a resposta como Mixed Content/CORS).
        log.exception(
            "medpag.unhandled_error",
            path=request.url.path,
            method=request.method,
            erro=str(exc),
            tipo=type(exc).__name__,
        )
        # Aplica CORS manualmente no 500 — o middleware CORS pode não rodar
        # em alguns caminhos de erro (ex.: erro durante serialização do
        # response_model), e sem CORS o browser oculta o status real e
        # reporta como "Network Error" no axios.
        origin = request.headers.get("origin", "")
        cors_headers: dict[str, str] = {}
        if origin:
            allowed = origin in settings.cors_origins_list
            if not allowed and settings.CORS_ORIGIN_REGEX:
                import re

                allowed = bool(re.match(settings.CORS_ORIGIN_REGEX, origin))
            if allowed:
                cors_headers["Access-Control-Allow-Origin"] = origin
                cors_headers["Access-Control-Allow-Credentials"] = "true"
                cors_headers["Vary"] = "Origin"

        return JSONResponse(
            status_code=500,
            headers=cors_headers,
            content={
                "success": False,
                "error": {
                    "code": "ERRO_INTERNO",
                    "message": f"Erro interno: {type(exc).__name__}: {exc}",
                },
            },
        )


def create_app() -> FastAPI:
    """Factory da aplicação FastAPI."""
    _configure_logging()

    app = FastAPI(
        title="MedPag API",
        description="Sistema de pagamentos em massa para o setor de saúde",
        version="0.1.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=settings.CORS_ORIGIN_REGEX or None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_exception_handlers(app)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Healthcheck simples (usado pelo Docker)."""
        return {"status": "ok", "version": "0.1.0"}

    # Routers da API
    from app.api import admin, auth, clientes, lotes, pagamentos

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
    app.include_router(clientes.router, prefix="/api/clientes", tags=["clientes"])
    app.include_router(lotes.router, prefix="/api/lotes", tags=["lotes"])
    app.include_router(pagamentos.router, prefix="/api/pagamentos", tags=["pagamentos"])

    return app


app = create_app()
