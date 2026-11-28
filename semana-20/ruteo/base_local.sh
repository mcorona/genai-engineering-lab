#!/usr/bin/env bash
# Week 20, activity 4, R0: the CI database on the Mac, as the eval-semana-17 workflow builds it ($0, synthetic data).
#
#   semana-20/ruteo/base_local.sh            (re)creates it and prints the two exports for r0_local.py
#   semana-20/ruteo/base_local.sh --borrar   removes it
#
# An ephemeral pgvector/pgvector:pg16 container on 127.0.0.1 only, then week 7's seed 42, the legacy schema and the
# week 13 ARTNOT view. Running it again starts from scratch, so it always ends in the same state. The passwords are the
# CI's (the data is synthetic and the port is local).
set -euo pipefail
cd "$(dirname "$0")/../.."
NOMBRE=s20-r0-legado
PUERTO=55432
docker rm -f "$NOMBRE" >/dev/null 2>&1 || true
if [[ "${1:-}" == "--borrar" ]]; then
  echo "removed $NOMBRE"
  exit 0
fi
docker run -d --rm --name "$NOMBRE" -p "127.0.0.1:$PUERTO:5432" \
  -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=ci-admin -e POSTGRES_DB=inventory pgvector/pgvector:pg16 >/dev/null
export PG_ADMIN_DSN="postgresql://admin:ci-admin@localhost:$PUERTO/inventory"
for _ in $(seq 1 60); do
  pg_isready -q -h localhost -p "$PUERTO" -U admin -d inventory && break
  sleep 1
done
sleep 2   # the image restarts once after its init scripts
until pg_isready -q -h localhost -p "$PUERTO" -U admin -d inventory; do sleep 1; done
.venv/bin/python semana-07/ci/preparar_base.py
psql "$PG_ADMIN_DSN" -q -v ON_ERROR_STOP=1 -f semana-10/legado/legado.sql >/dev/null
psql "$PG_ADMIN_DSN" -q -v ON_ERROR_STOP=1 -f semana-13/seguridad/artnot.sql >/dev/null
echo "export PG_ADMIN_DSN=$PG_ADMIN_DSN"
echo "export PG_DSN=postgresql://copilot_ro:ci-ro@localhost:$PUERTO/inventory"
