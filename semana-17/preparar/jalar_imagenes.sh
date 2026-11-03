#!/usr/bin/env bash
# Week 17 preparation: pulls the pinned images of preparar/versiones.json (Langfuse v4, its dependencies, the
# OpenTelemetry Collector and Keycloak), so activity 2 does not wait on downloads. About 3 to 4 GB. $0.
# Prints the digest of each image: activity 1 records them in versiones.json.
#
#   semana-17/preparar/jalar_imagenes.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
python3 - "$DIR/versiones.json" <<'EOF' | while read -r nombre imagen; do
import json, sys
for k, v in json.load(open(sys.argv[1]))["imagenes"].items():
    print(k, v)
EOF
  echo "[imagenes] $nombre: $imagen"
  docker pull -q "$imagen" >/dev/null
  echo "            $(docker image inspect --format '{{index .RepoDigests 0}}' "$imagen")"
done
echo "[imagenes] listas"
