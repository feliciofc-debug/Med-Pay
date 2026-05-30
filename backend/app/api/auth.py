"""Rotas de autenticação."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import ClienteMini, LoginRequest, RefreshRequest, TokenPair, UserOut
from app.services.auth import AuthService
from app.services.feature_flags import features_resolvidas

router = APIRouter()


def _set_auth_cookie(response: Response, access_token: str) -> None:
    """Define cookie httpOnly com o access_token.

    - HttpOnly: bloqueia acesso via JS (anti-XSS)
    - Secure: só envia em HTTPS (prod)
    - SameSite=none em produção (frontend e backend em domínios diferentes:
      Vercel + Render). SameSite=lax em dev (mesmo domínio localhost).
    """
    samesite_value: str = "none" if settings.is_production else "lax"
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.is_production,
        samesite=samesite_value,  # type: ignore[arg-type]
        max_age=settings.JWT_ACCESS_EXPIRE_MINUTES * 60,
        path="/",
    )


@router.post("/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Autentica usuário e retorna par de tokens.

    Em produção, o `access_token` também é retornado em cookie httpOnly
    para o frontend usar — o JSON é mantido para clientes que preferem
    armazenar manualmente (mobile, SDKs).
    """
    service = AuthService(db)
    user = await service.autenticar(payload.email, payload.password)
    tokens = service.gerar_tokens(user)
    _set_auth_cookie(response, tokens.access_token)
    return tokens


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Troca refresh_token por par novo de tokens."""
    service = AuthService(db)
    tokens = await service.refresh(payload.refresh_token)
    _set_auth_cookie(response, tokens.access_token)
    return tokens


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    """Limpa o cookie de autenticação."""
    response.delete_cookie(key="access_token", path="/")
    return {"success": True}


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    """Retorna o usuário autenticado + contexto do tenant.

    Inclui os 3 eixos do cliente (tipo, modo_pagamento e o dict de
    features resolvido) pro frontend derivar menu/dashboard dinamicamente,
    sem `if tipo == 'hospital'` espalhado.
    """
    cliente_out: ClienteMini | None = None
    cliente = current_user.cliente
    if cliente is not None:
        cliente_out = ClienteMini(
            id=cliente.id,
            nome=cliente.nome,
            tipo=cliente.tipo,
            modo_pagamento=cliente.modo_pagamento,
            features=features_resolvidas(cliente),
        )

    return UserOut(
        id=current_user.id,
        email=current_user.email,
        nome=current_user.nome,
        role=current_user.role,
        ativo=current_user.ativo,
        cliente_id=current_user.cliente_id,
        cliente=cliente_out,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
    )
