"""Testes de segurança: hashing de senha e JWT."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from jose import jwt as jose_jwt

from app.core.config import settings
from app.core.security import (
    JWTError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_e_diferente_da_senha(self) -> None:
        senha = "minha_senha_super_segura"
        hashed = hash_password(senha)
        assert hashed != senha

    def test_verify_correto(self) -> None:
        senha = "minha_senha_super_segura"
        hashed = hash_password(senha)
        assert verify_password(senha, hashed) is True

    def test_verify_errado(self) -> None:
        hashed = hash_password("senha_certa")
        assert verify_password("senha_errada", hashed) is False

    def test_hash_da_mesma_senha_e_diferente(self) -> None:
        """bcrypt usa salt aleatório."""
        h1 = hash_password("senha")
        h2 = hash_password("senha")
        assert h1 != h2
        assert verify_password("senha", h1)
        assert verify_password("senha", h2)


class TestAccessToken:
    def test_cria_e_decodifica(self) -> None:
        user_id = uuid4()
        token = create_access_token(user_id)
        payload = decode_token(token)
        assert payload["sub"] == str(user_id)
        assert payload["type"] == "access"

    def test_extra_claims(self) -> None:
        user_id = uuid4()
        token = create_access_token(user_id, extra_claims={"role": "APROVADOR"})
        payload = decode_token(token)
        assert payload["role"] == "APROVADOR"

    def test_expiration_no_payload(self) -> None:
        user_id = uuid4()
        token = create_access_token(user_id)
        payload = decode_token(token)
        agora = datetime.now(UTC).timestamp()
        # Expiração deve estar no futuro próximo
        assert payload["exp"] > agora
        assert payload["exp"] <= agora + (settings.JWT_ACCESS_EXPIRE_MINUTES * 60) + 5


class TestRefreshToken:
    def test_cria_refresh(self) -> None:
        user_id = uuid4()
        token = create_refresh_token(user_id)
        payload = decode_token(token)
        assert payload["type"] == "refresh"
        assert payload["sub"] == str(user_id)

    def test_refresh_dura_mais_que_access(self) -> None:
        user_id = uuid4()
        access = decode_token(create_access_token(user_id))
        refresh = decode_token(create_refresh_token(user_id))
        assert refresh["exp"] > access["exp"]


class TestTokenInvalido:
    def test_token_lixo(self) -> None:
        with pytest.raises(JWTError):
            decode_token("lixo.aqui.token")

    def test_token_assinado_com_outra_chave(self) -> None:
        payload = {
            "sub": str(uuid4()),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        }
        token_falso = jose_jwt.encode(payload, "outra_chave_qualquer", algorithm="HS256")
        with pytest.raises(JWTError):
            decode_token(token_falso)

    def test_token_expirado(self) -> None:
        payload = {
            "sub": str(uuid4()),
            "exp": datetime.now(UTC) - timedelta(seconds=1),
            "iat": datetime.now(UTC) - timedelta(minutes=10),
            "type": "access",
        }
        token = jose_jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        # Pequena espera pra garantir que está expirado
        time.sleep(0.01)
        with pytest.raises(JWTError):
            decode_token(token)
