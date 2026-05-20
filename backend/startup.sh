#!/bin/bash
# Script de inicialização do backend MedPag em produção.
# Roda migrations, popula dados iniciais idempotentes, e sobe o uvicorn.
#
# Idempotência: rodar várias vezes é seguro. create_admin e seed_demo
# verificam se já existe e não duplicam nada.

set -euo pipefail

echo "=========================================="
echo "MedPag Backend — startup"
echo "Environment: ${ENVIRONMENT:-development}"
echo "=========================================="

# 1. Aplicar migrations
echo "[1/3] Aplicando migrations Alembic..."
alembic upgrade head

# 2. Criar admin se não existir (Thiago / Felício)
echo "[2/3] Garantindo usuário ADMIN..."
python -m app.scripts.create_admin || echo "    (admin já existe, prosseguindo)"

# 3. Popular dados de demonstração se SEED_DEMO=true
if [ "${SEED_DEMO:-false}" = "true" ]; then
    echo "[3/3] Populando dados de demonstração..."
    python -m app.scripts.seed_demo || echo "    (seed_demo já rodou ou houve erro não-fatal, prosseguindo)"
else
    echo "[3/3] SEED_DEMO != true — pulando seed de demonstração"
fi

# 4. Subir uvicorn
echo "=========================================="
echo "Iniciando uvicorn na porta ${PORT:-8000}..."
echo "=========================================="
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
