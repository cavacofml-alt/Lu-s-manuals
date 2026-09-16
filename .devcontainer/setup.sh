#!/usr/bin/env bash
# One-time setup for a Codespace or any devcontainer.
# Everything runs in containers, so this matches the local-PC deployment exactly —
# no separate "cloud version" of the stack to diverge from.
set -euo pipefail

echo "▸ starting PostgreSQL 16 + pgvector"
docker compose up -d postgres
until docker compose exec -T postgres pg_isready -U docintel >/dev/null 2>&1; do sleep 1; done

echo "▸ installing backend dependencies"
cd backend
python -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e ".[dev]"

echo "▸ applying migrations"
.venv/bin/alembic upgrade head

echo "▸ installing frontend dependencies"
cd ../frontend && npm install --silent --no-fund --no-audit

cat <<'MSG'

  Ready.

    make test     run the suite
    make egress   regenerate the egress matrix
    make up       start api + worker + postgres

  Documents are uploaded through the app once STEP 3 lands; they are never
  committed to this repository (it is public — see docs/audit/README.md).

MSG
