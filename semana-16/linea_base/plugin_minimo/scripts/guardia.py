"""The spike's PreToolUse hook: blocks writes.

- Write/Edit/MultiEdit/NotebookEdit outside the project's `auditoria/`: blocked.
- Bash with write SQL (INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, COPY ... FROM) or with a
  `psql -c` that is not a SELECT: blocked.
It blocks with exit code 2 and the reason on stderr (Claude receives it). Everything else: exit 0 with no text.
"""
import json
import os
import re
import sys

ESCRITURA_SQL = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|MERGE|COPY\s+\w+\s+FROM|lo_import|lo_create)\b", re.I)
HERRAMIENTAS_ESCRITURA = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def decidir(evento: dict) -> tuple[int, str]:
    herramienta = evento.get("tool_name", "")
    entrada = evento.get("tool_input") or {}
    proyecto = os.path.realpath(evento.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    if herramienta in HERRAMIENTAS_ESCRITURA:
        ruta = entrada.get("file_path") or entrada.get("notebook_path") or ""
        destino = os.path.realpath(os.path.join(proyecto, ruta))
        permitido = os.path.join(proyecto, "auditoria") + os.sep
        if not destino.startswith(permitido):
            return 2, f"lb-spike: escritura bloqueada fuera de auditoria/: {ruta}"
    if herramienta == "Bash":
        comando = entrada.get("command", "")
        if ESCRITURA_SQL.search(comando):
            return 2, "lb-spike: SQL de escritura bloqueado (solo lectura)"
    return 0, ""


def main() -> int:
    try:
        codigo, motivo = decidir(json.load(sys.stdin))
    except Exception as e:  # noqa: BLE001  fail closed: an input that is not understood does not pass
        codigo, motivo = 2, f"lb-spike: guardia sin decisión ({type(e).__name__}); se bloquea"
    if motivo:
        print(motivo, file=sys.stderr)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
