#!/usr/bin/env bash
# Week 15, activity 1: one virtual environment per framework (they pin mutually incompatible versions of mcp, a2a-sdk
# and litellm). Idempotent. Uses uv if it is installed; otherwise python3 -m venv + pip. No API, $0.
#   ./linea_base/preparar.sh        (from semana-15/)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3.13}
command -v "$PY" >/dev/null || PY=python3
mkdir -p .venvs
for n in lg st oa adk; do
  if [[ ! -x .venvs/$n/bin/python ]]; then
    if command -v uv >/dev/null; then uv venv -q -p "$PY" ".venvs/$n"; else "$PY" -m venv ".venvs/$n"; fi
  fi
  if command -v uv >/dev/null; then uv pip install -q -p ".venvs/$n/bin/python" -r "linea_base/requisitos/$n.txt"
  else ".venvs/$n/bin/pip" install -q -r "linea_base/requisitos/$n.txt"; fi
  echo "[preparar] $n ready: $(.venvs/$n/bin/python -c 'import importlib.metadata as m; print("mcp", m.version("mcp"))')"
done
