#!/usr/bin/env bash
# LegacyBridge v1: one bring-up for what weeks 7 to 17 start separately. Idempotent. Secrets are generated per machine by each piece and
# never printed. The MCP server and the purchasing specialist are started by `python -m legacybridge` itself, for the life of a command.
#
#   semana-18/legacybridge/arrancar.sh             start or confirm everything, then print the state
#   semana-18/legacybridge/arrancar.sh --estado    only the state
#   semana-18/legacybridge/arrancar.sh --detener   stop Keycloak and the observability stack (data kept; the database is left running)
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
RAIZ="$(cd "$DIR/../.." && pwd)"
CONTENEDOR_BD="${LEGACYBRIDGE_BD:-copilot-db}"

sonda() { curl -fsS -o /dev/null --max-time 3 "$1" 2>/dev/null && echo up || echo DOWN; }
estado() {
  echo "database   ($CONTENEDOR_BD): $(docker inspect -f '{{.State.Status}}' "$CONTENEDOR_BD" 2>/dev/null || echo missing)"
  echo "keycloak   :8180 $(sonda http://127.0.0.1:8180/realms/legacybridge/.well-known/openid-configuration)"
  echo "langfuse   :3100 $(sonda http://127.0.0.1:3100/api/public/health)"
  echo "collector  :4318 $(sonda http://127.0.0.1:13133/)"
  echo "specialist env : $([[ -x "$RAIZ/semana-15/.venvs/st/bin/python" ]] && echo ready || echo missing)"
  echo "approvers      : $([[ -f "$DIR/.secretos.env" ]] && echo ready || echo missing)"
}

case "${1:-}" in
  --estado) estado; exit 0 ;;
  --detener) "$RAIZ/semana-14/auth/arrancar.sh" --detener; "$RAIZ/semana-17/observabilidad/arrancar.sh" --detener; exit 0 ;;
  "") ;;
  *) echo "usage: $0 [--estado|--detener]" >&2; exit 2 ;;
esac

command -v docker >/dev/null || { echo "[v1] docker is required" >&2; exit 1; }
: "${PG_ADMIN_DSN:?[v1] set PG_ADMIN_DSN to the lab database (see semana-07/ci/preparar_base.py)}"
docker start "$CONTENEDOR_BD" >/dev/null 2>&1 || echo "[v1] container $CONTENEDOR_BD not started here; using PG_ADMIN_DSN as given"
"$RAIZ/semana-14/auth/arrancar.sh" | tail -1
"$RAIZ/semana-17/observabilidad/arrancar.sh" | tail -1
[[ -x "$RAIZ/semana-15/.venvs/st/bin/python" ]] || ( cd "$RAIZ/semana-15" && ./linea_base/preparar.sh )
( cd "$RAIZ/semana-18" && uv run --group semana17 python -m legacybridge.identidades )
estado
