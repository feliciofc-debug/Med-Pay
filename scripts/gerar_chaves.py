"""Gera chaves seguras para o .env do MedPag.

Uso:
    python scripts/gerar_chaves.py

Imprime as chaves no formato pronto pra copiar pro .env.

Requer: cryptography (já está em backend/requirements.txt; se rodar fora
do ambiente do backend, instale: pip install cryptography)
"""

from __future__ import annotations

import secrets
import sys


def main() -> None:
    print("=" * 60)
    print("MedPag — Chaves geradas")
    print("=" * 60)
    print()

    # SECRET_KEY (JWT)
    secret_key = secrets.token_urlsafe(48)
    print(f"SECRET_KEY={secret_key}")
    print()

    # ENCRYPTION_KEY (Fernet)
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print("ENCRYPTION_KEY=<INSTALE cryptography E RODE NOVAMENTE>")
        print()
        print("    pip install cryptography")
        print()
        sys.exit(1)

    encryption_key = Fernet.generate_key().decode()
    print(f"ENCRYPTION_KEY={encryption_key}")
    print()

    print("=" * 60)
    print("Cole essas linhas no seu .env (substituindo os valores antigos).")
    print("NUNCA commite o .env no git.")
    print("=" * 60)


if __name__ == "__main__":
    main()
