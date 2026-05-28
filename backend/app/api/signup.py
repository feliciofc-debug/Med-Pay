"""Endpoint público de onboarding self-service.

POST /api/signup
    Cria cliente + user admin + (best-effort) customer Asaas e devolve
    tokens pra logar direto. Nenhuma autenticação prévia necessária.

Rate-limit é responsabilidade do gateway (Cloudflare/Vercel/Render).
Em prod recomendamos limitar a ~5 signups/hora por IP pra evitar abuse.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _set_auth_cookie  # reusa helper de cookie
from app.core.config import settings
from app.core.deps import get_db
from app.core.security import create_access_token, create_refresh_token
from app.schemas.auth import UserOut
from app.schemas.signup import SignupRequest, SignupResposta
from app.services.signup_service import signup as criar_conta

router = APIRouter()


@router.post(
    "",
    response_model=SignupResposta,
    status_code=status.HTTP_201_CREATED,
)
async def signup_endpoint(
    payload: SignupRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> SignupResposta:
    """Cria conta self-service.

    Funciona mesmo sem ASAAS_API_KEY — só pula a criação de customer
    Asaas e o cliente pode sincronizar depois.
    """
    cliente, user = await criar_conta(
        db,
        plano_slug=payload.plano_slug,
        nome_empresa=payload.nome_empresa,
        cnpj=payload.cnpj,
        email_contato=payload.email_contato,
        telefone=payload.telefone,
        admin_nome=payload.admin_nome,
        admin_email=payload.admin_email,
        admin_senha=payload.admin_senha,
    )

    # Tokens pra logar direto (sem ele ter que ir pra /login)
    access = create_access_token({"sub": str(user.id), "type": "access"})
    refresh = create_refresh_token({"sub": str(user.id), "type": "refresh"})
    _set_auth_cookie(response, access)
    _ = settings  # silence noqa

    return SignupResposta(
        cliente_id=cliente.id,
        nome_empresa=cliente.nome,
        status_assinatura=cliente.status_assinatura,
        trial_termina_em=cliente.trial_termina_em,
        user=UserOut.model_validate(user),
        access_token=access,
        refresh_token=refresh,
    )
