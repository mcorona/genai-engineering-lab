#!/usr/bin/env bash
# Semana 17, actividad 2: stack de observabilidad (Langfuse v4 autoalojado + OpenTelemetry Collector).
# Idempotente: correrlo de nuevo no duplica nada. Los secretos se generan una vez en .secretos.env (chmod 600,
# ignorado por Git) y NUNCA se imprimen. Las imágenes salen por digest de ../preparar/versiones.json.
#
#   ./arrancar.sh              arranca (o confirma que ya corre) y espera a que todo responda
#   ./arrancar.sh --estado     muestra los contenedores y la salud de Langfuse y del Collector
#   ./arrancar.sh --detener    detiene los contenedores (conserva volúmenes y datos)
#   ./arrancar.sh --reiniciar  detiene y vuelve a arrancar (los datos persisten)
#   ./arrancar.sh --borrar     borra contenedores, volúmenes, red y datos/ (conserva .secretos.env)
#   ./arrancar.sh --borrar --secretos   lo mismo y además .secretos.env (el siguiente arranque genera claves nuevas)
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SECRETOS="$DIR/.secretos.env"
DATOS="$DIR/datos"
VERSIONES="$DIR/../preparar/versiones.json"
PROYECTO=s17-observabilidad
PUERTOS="3100 4317 4318 13133"
LANGFUSE=http://127.0.0.1:3100
COLLECTOR_SALUD=http://127.0.0.1:13133

uso() { sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

accion=arrancar
con_secretos=no
for a in "$@"; do
  case "$a" in
    --estado) accion=estado ;;
    --detener) accion=detener ;;
    --reiniciar) accion=reiniciar ;;
    --borrar) accion=borrar ;;
    --secretos) con_secretos=si ;;
    -h|--help) uso ;;
    *) echo "opción desconocida: $a" >&2; uso ;;
  esac
done
if [[ "$con_secretos" == si && "$accion" != borrar ]]; then echo "--secretos solo se usa con --borrar" >&2; exit 2; fi

command -v docker >/dev/null || { echo "[stack] falta Docker" >&2; exit 1; }
command -v openssl >/dev/null || { echo "[stack] falta openssl (genera los secretos)" >&2; exit 1; }

# $1 = bytes aleatorios; imprime 2*$1 caracteres hexadecimales
aleatorio() { openssl rand -hex "$1"; }

generar_secretos() {
  ( umask 077
    pk="pk-lf-$(aleatorio 8)"; sk="sk-lf-$(aleatorio 16)"
    {
      echo "# Generado por arrancar.sh el $(date -u +%FT%TZ). No versionar."
      echo "POSTGRES_PASSWORD=$(aleatorio 16)"
      echo "CLICKHOUSE_PASSWORD=$(aleatorio 16)"
      echo "MINIO_ROOT_PASSWORD=$(aleatorio 16)"
      echo "REDIS_AUTH=$(aleatorio 16)"
      echo "SALT=$(aleatorio 16)"
      echo "ENCRYPTION_KEY=$(aleatorio 32)"
      echo "NEXTAUTH_SECRET=$(aleatorio 16)"
      echo "LANGFUSE_USER_PASSWORD=$(aleatorio 12)"
      echo "LANGFUSE_PUBLIC_KEY=$pk"
      echo "LANGFUSE_SECRET_KEY=$sk"
      echo "LANGFUSE_AUTH=$(printf '%s:%s' "$pk" "$sk" | base64 | tr -d '\n')"
    } >"$SECRETOS" )
  chmod 600 "$SECRETOS"
  echo "[stack] secretos nuevos en .secretos.env ($(grep -c '=' "$SECRETOS") variables, permisos 600; no se imprimen)"
}

# Exporta IMG_*: repositorio@digest de versiones.json (el tag se descarta: lo fijado es el digest).
cargar_imagenes() {
  local lineas linea
  lineas="$(python3 - "$VERSIONES" <<'PY'
import json, sys
v = json.load(open(sys.argv[1], encoding="utf-8"))
mapa = {"langfuse-web": "IMG_LANGFUSE_WEB", "langfuse-worker": "IMG_LANGFUSE_WORKER", "clickhouse": "IMG_CLICKHOUSE",
        "minio": "IMG_MINIO", "redis": "IMG_REDIS", "postgres": "IMG_POSTGRES", "otel-collector": "IMG_COLLECTOR"}
for nombre, var in mapa.items():
    print(f"{var}={v['imagenes'][nombre].rsplit(':', 1)[0]}@{v['digests'][nombre]}")
PY
)"
  while IFS= read -r linea; do export "$linea"; done <<<"$lineas"
}

if [[ -f "$SECRETOS" ]]; then ENVFILE="$SECRETOS"; chmod 600 "$SECRETOS"; else ENVFILE=/dev/null; fi
if [[ ! -f "$SECRETOS" && ( "$accion" == arrancar || "$accion" == reiniciar ) ]]; then
  generar_secretos; ENVFILE="$SECRETOS"
fi
cargar_imagenes
export HOST_UID="$(id -u)" HOST_GID="$(id -g)"
compose() { docker compose -p "$PROYECTO" -f "$DIR/docker-compose.yml" --env-file "$ENVFILE" "$@"; }
hay_contenedores() { [[ -n "$(docker ps -aq --filter "label=com.docker.compose.project=$PROYECTO")" ]]; }

revisar_puertos() {
  hay_contenedores && return 0                 # the stack's own containers hold them
  local p ocupados=""
  for p in $PUERTOS; do nc -z 127.0.0.1 "$p" >/dev/null 2>&1 && ocupados="$ocupados $p"; done
  if [[ -n "$ocupados" ]]; then echo "[stack] puertos en uso:$ocupados (¿otro servicio del laboratorio?)" >&2; exit 3; fi
}

esperar() {
  local t0=$SECONDS
  echo -n "[stack] esperando a Langfuse (3100) y al Collector (13133) "
  until curl -fsS -o /dev/null "$LANGFUSE/api/public/health" 2>/dev/null && curl -fsS -o /dev/null "$COLLECTOR_SALUD/" 2>/dev/null; do
    if (( SECONDS - t0 > 300 )); then echo " no respondieron en 300 s" >&2; compose ps >&2; exit 1; fi
    echo -n "."; sleep 3
  done
  echo " listo en $((SECONDS - t0)) s"
}

arrancar() {
  revisar_puertos
  mkdir -p "$DATOS"
  compose up -d --quiet-pull
  esperar
  echo "[stack] Langfuse:   $LANGFUSE (usuario admin@lab.example; contraseña y claves del proyecto en .secretos.env)"
  echo "[stack] OTLP HTTP:  http://127.0.0.1:4318/v1/traces   OTLP gRPC: 127.0.0.1:4317   salud: $COLLECTOR_SALUD"
  echo "[stack] trazas (ya redactadas): $DATOS/trazas.jsonl"
}

borrar() {
  compose down -v --remove-orphans
  rm -rf "$DATOS"
  [[ "$con_secretos" == si ]] && rm -f "$SECRETOS"
  local c v r
  c="$(docker ps -aq --filter "label=com.docker.compose.project=$PROYECTO" | wc -l | tr -d ' ')"
  v="$(docker volume ls -q --filter "label=com.docker.compose.project=$PROYECTO" | wc -l | tr -d ' ')"
  r="$(docker network ls -q --filter "label=com.docker.compose.project=$PROYECTO" | wc -l | tr -d ' ')"
  echo "[stack] restos tras borrar: $c contenedores, $v volúmenes, $r redes; datos/ $([[ -e "$DATOS" ]] && echo existe || echo borrado)"
  [[ "$c$v$r" == 000 && ! -e "$DATOS" ]] || { echo "[stack] el borrado no fue completo" >&2; exit 1; }
}

case "$accion" in
  arrancar) arrancar ;;
  reiniciar) compose stop; arrancar ;;
  detener) compose stop ;;
  borrar) borrar ;;
  estado)
    compose ps
    echo "Langfuse /api/public/health: $(curl -s -o /dev/null -w '%{http_code}' "$LANGFUSE/api/public/health" || true)"
    echo "Collector health_check:      $(curl -s -o /dev/null -w '%{http_code}' "$COLLECTOR_SALUD/" || true)" ;;
esac
