"""The spike's PostToolUse hook: one JSONL line per Bash command in auditoria/bitacora.jsonl (the report's evidence)."""
import json
import os
import sys
import time

evento = json.load(sys.stdin)
proyecto = evento.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
ruta = os.path.join(proyecto, "auditoria", "bitacora.jsonl")
os.makedirs(os.path.dirname(ruta), exist_ok=True)
with open(ruta, "a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": round(time.time(), 3), "herramienta": evento.get("tool_name"),
                        "comando": (evento.get("tool_input") or {}).get("command", "")[:500]}, ensure_ascii=False) + "\n")
