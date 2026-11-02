"""Shared helpers for the plugin's hooks: the read-only SQL check, subagent allowlists and per-session state."""
from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PREFIJO = "mcp__plugin_legacy-schema-audit_legacy-sql__"
HERRAMIENTAS_PROPIAS = {PREFIJO + n for n in ("list_objects", "describe_object", "profile_table", "run_select")}
# Remote legacy servers (week 14 tool names), whatever name the client registered them under.
REMOTAS = ("describir_esquema", "muestrear_valores", "validar_sql", "ejecutar_sql")
SQL_LIBRE = ("run_select", "ejecutar_sql", "validar_sql")


def es_herramienta_bd(nombre: str) -> bool:
    return nombre in HERRAMIENTAS_PROPIAS or (nombre.startswith("mcp__") and nombre.rsplit("__", 1)[-1] in REMOTAS)


def corto(nombre: str) -> str:
    return nombre.rsplit("__", 1)[-1] if nombre.startswith("mcp__") else nombre


ESCRITURA_SQL = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|CALL|DO|LOCK|"
                           r"VACUUM|REINDEX|CLUSTER|SET|RESET|BEGIN|COMMIT|ROLLBACK|INTO)\b|\b(pg_|lo_)\w*\s*\(|"
                           r"\b(dblink|set_config|current_setting|nextval|setval|query_to_xml|table_to_xml)\s*\(", re.I)


def check_read_only(sql: str) -> None:
    """Same check the bundled server applies (servidor/sql_lectura.py, sqlglot), loaded by path. Raises on anything but
    one read-only SELECT. When sqlglot is not importable (a hook run by a bare system python3, as in `plugin eval`
    sandboxes) a stricter regex check takes its place: one statement, SELECT or WITH, no write keyword anywhere."""
    try:
        spec = importlib.util.spec_from_file_location("sql_lectura", RAIZ / "servidor" / "sql_lectura.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except ImportError:
        texto = re.sub(r"'(?:[^']|'')*'", "''", sql).strip().rstrip(";")
        if ";" in texto or not re.match(r"^\(?\s*(SELECT|WITH)\b", texto, re.I) or ESCRITURA_SQL.search(texto):
            raise ValueError("write_blocked: only one read-only SELECT is allowed (regex check, sqlglot unavailable)")
        return
    try:
        mod.check_read_only(sql)
    except mod.ToolError as e:
        raise ValueError(f"{e.kind}: {e.message}") from None


def herramientas_de_agentes() -> dict[str, set[str]]:
    """Allowlist of each plugin subagent, read from the `tools:` line of agents/*.md (the single source of truth)."""
    agentes = {}
    for f in sorted((RAIZ / "agents").glob("*.md")):
        m = re.match(r"^---\n(.*?)\n---\n", f.read_text(encoding="utf-8"), re.S)
        campos = dict(re.findall(r"^([\w-]+):\s*(.*)$", m.group(1), re.M)) if m else {}
        agentes[campos.get("name", f.stem)] = {t.strip() for t in campos.get("tools", "").split(",") if t.strip()}
    return agentes


def agente_del_plugin(agent_type: str | None) -> str | None:
    """'legacy-schema-audit:perfilador' or 'perfilador' -> 'perfilador' when it is one of this plugin's subagents."""
    if not agent_type:
        return None
    nombre = agent_type.split(":")[-1]
    if ":" in agent_type and not agent_type.startswith("legacy-schema-audit:"):
        return None
    return nombre if nombre in herramientas_de_agentes() else None


def dir_estado(arg: str | None) -> Path:
    for d in (arg, os.environ.get("CLAUDE_PLUGIN_DATA")):
        if d and not d.startswith("${"):
            return Path(d)
    return Path.home() / ".cache" / "legacy-schema-audit"


def ruta_estado(directorio: Path, session_id: str) -> Path:
    seguro = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "sin-sesion")
    return directorio / "sesiones" / f"{seguro}.json"


def leer_estado(directorio: Path, session_id: str) -> dict | None:
    p = ruta_estado(directorio, session_id)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def escribir_estado(directorio: Path, session_id: str, estado: dict) -> None:
    p = ruta_estado(directorio, session_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(estado, ensure_ascii=False), encoding="utf-8")
    os.chmod(p, 0o600)


def dsn_configurado(env=os.environ) -> str:
    dsn = env.get("CLAUDE_PLUGIN_OPTION_PG_DSN") or ""
    if not dsn or dsn.startswith("${"):
        dsn = env.get("LEGACY_AUDIT_DSN", "")
    return dsn


def esquema_configurado(env=os.environ) -> str:
    e = (env.get("CLAUDE_PLUGIN_OPTION_AUDIT_SCHEMA") or "").strip().lower()
    return "legado" if not e or e.startswith("${") else e
