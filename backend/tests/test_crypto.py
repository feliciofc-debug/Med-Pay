"""Testes de criptografia de campos sensíveis."""

from __future__ import annotations

import pytest

from app.core.crypto import (
    decrypt,
    encrypt,
    hash_for_lookup,
    mask_conta,
    mask_cpf,
)


class TestEncryptDecrypt:
    """Roundtrip de criptografia."""

    def test_roundtrip_cpf(self) -> None:
        cpf = "12345678901"
        ciphertext = encrypt(cpf)
        assert isinstance(ciphertext, bytes)
        assert ciphertext != cpf.encode()
        assert decrypt(ciphertext) == cpf

    def test_roundtrip_unicode(self) -> None:
        texto = "José da Silva — açúcar"
        assert decrypt(encrypt(texto)) == texto

    def test_encrypt_vazio_levanta_erro(self) -> None:
        with pytest.raises(ValueError):
            encrypt("")

    def test_encrypt_mesma_string_gera_bytes_diferentes(self) -> None:
        """Fernet usa IV aleatório — duas criptografias da mesma string
        produzem ciphertexts diferentes (boa propriedade de segurança)."""
        cpf = "12345678901"
        c1 = encrypt(cpf)
        c2 = encrypt(cpf)
        assert c1 != c2  # IVs diferentes
        assert decrypt(c1) == decrypt(c2) == cpf


class TestHashForLookup:
    """Hash determinístico para busca."""

    def test_hash_e_deterministico(self) -> None:
        cpf = "12345678901"
        assert hash_for_lookup(cpf) == hash_for_lookup(cpf)

    def test_hash_difere_para_strings_diferentes(self) -> None:
        assert hash_for_lookup("12345678901") != hash_for_lookup("12345678902")

    def test_hash_tem_64_caracteres_hex(self) -> None:
        h = hash_for_lookup("12345678901")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestMascaras:
    """Mascaramento para LGPD."""

    def test_mask_cpf_completo(self) -> None:
        assert mask_cpf("12345678901") == "XXX.XXX.XXX-01"

    def test_mask_cpf_curto_retorna_estrelas(self) -> None:
        assert mask_cpf("12") == "***"

    def test_mask_cpf_vazio(self) -> None:
        assert mask_cpf("") == "***"

    def test_mask_conta_completa(self) -> None:
        assert mask_conta("123456789") == "****6789"

    def test_mask_conta_curta(self) -> None:
        assert mask_conta("12") == "****"

    def test_mask_conta_vazia(self) -> None:
        assert mask_conta("") == "****"
