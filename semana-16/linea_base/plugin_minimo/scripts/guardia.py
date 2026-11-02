"""Hook PreToolUse del spike: bloquea escrituras.

- Write/Edit/MultiEdit/NotebookEdit fuera de `auditoria/` del proyecto: bloqueado.
- Bash con SQL de escritura (INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, COPY ... FROM) o con
  `psql -c` que no sea SELECT: bloqueado.
Bloquea con código de salida 2 y el motivo en stderr (Claude lo recibe). Todo lo demás: salida 0 sin texto.
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
    except Exception as e:  # noqa: BLE001  falla cerrada: una entrada que no se entiende no pasa
        codigo, motivo = 2, f"lb-spike: guardia sin decisión ({type(e).__name__}); se bloquea"
    if motivo:
        print(motivo, file=sys.stderr)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
