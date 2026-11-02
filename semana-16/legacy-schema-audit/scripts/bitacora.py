"""PostToolUse hook of legacy-schema-audit: appends one JSONL line per database tool call to auditoria/bitacora.jsonl.

Each line: timestamp, session, agent (the subagent type, or "main"), tool, the SQL (for free-SQL tools) or the
arguments, ok, rows returned, truncated, and the error type. Never the rows themselves: they can hold personal data.
The audit skill keeps only findings whose SQL is in this log (evidence for the report). Never blocks: exit 0.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun  # noqa: E402


def respuesta(r) -> dict:
    """The tool's JSON result, whatever shape Claude Code hands it over in (dict, MCP content list, text)."""
    if isinstance(r, dict) and "ok" in r:
        return r
    if isinstance(r, dict):
        if isinstance(r.get("structuredContent"), dict):
            return r["structuredContent"]
        r = r.get("content", r.get("result", r))
    if isinstance(r, list):
        r = next((b.get("text") for b in r if isinstance(b, dict) and b.get("type") == "text"), "")
    if isinstance(r, str):
        try:
            v = json.loads(r)
            return v if isinstance(v, dict) else {"ok": None}
        except json.JSONDecodeError:
            return {"ok": None, "error": {"type": "unparsed_response"}}
    return {"ok": None}


def entrada_bitacora(evento: dict) -> dict | None:
    herramienta = evento.get("tool_name") or ""
    if not comun.es_herramienta_bd(herramienta):
        return None
    args = dict(evento.get("tool_input") or {})
    res = respuesta(evento.get("tool_response"))
    nombre = comun.corto(herramienta)
    linea = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
             "session": evento.get("session_id"), "agent": evento.get("agent_type") or "main",
             "tool": nombre, "server": "legacy-sql" if herramienta in comun.HERRAMIENTAS_PROPIAS else "remote",
             "sql": args.pop("sql", None) if nombre in comun.SQL_LIBRE else None,
             "args": {k: v for k, v in args.items() if k != "sql"} or None,
             "ok": res.get("ok"), "rows": None, "truncated": res.get("truncated", res.get("truncado")),
             "error": None}
    filas = res.get("total_rows", res.get("total_filas", res.get("rows")))
    linea["rows"] = filas if isinstance(filas, int) else (len(filas) if isinstance(filas, list) else None)
    err = res.get("error")
    linea["error"] = (err.get("type") or err.get("tipo")) if isinstance(err, dict) else err
    if linea["ok"] is None and isinstance(evento.get("tool_response"), dict) and "isError" in evento["tool_response"]:
        linea["ok"] = not evento["tool_response"]["isError"]
    return linea


def main() -> int:
    try:
        evento = json.load(sys.stdin)
        linea = entrada_bitacora(evento)
        if linea is None:
            return 0
        destino = Path(evento.get("cwd") or os.getcwd()) / "auditoria" / "bitacora.jsonl"
        destino.parent.mkdir(parents=True, exist_ok=True)
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(linea, ensure_ascii=False, default=str) + "\n")
    except Exception as e:  # noqa: BLE001  the log never blocks the audit; the failure is reported
        print(f"legacy-schema-audit: could not write the query log ({type(e).__name__})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
