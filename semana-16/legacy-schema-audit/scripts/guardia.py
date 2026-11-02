"""PreToolUse hook of legacy-schema-audit: blocks with exit 2 (the reason goes to Claude on stderr).

1. SQL that is not one read-only SELECT, in the bundled server's run_select or a remote server's ejecutar_sql or
   validar_sql (same check as the server).
2. Database tools when the SessionStart check found a role that can write, or when that check did not run.
3. Bash against the database: database clients, connection strings, drivers, `docker exec`.
4. Reading secrets: .env files, the week 14 .secretos.env, .pgpass, .netrc, private keys, cloud credentials,
   ~/.ssh and ~/.aws (Read, Grep, Glob, NotebookRead and Bash).
5. Writes outside auditoria/ of the project (Write, Edit, MultiEdit, NotebookEdit, Bash redirections and
   file-changing commands), and deliverables that contain personal values (emails, phone numbers, RFC tax IDs).
6. A plugin subagent calling a tool outside the `tools:` list of its agents/*.md (hook input has agent_type).

Anything it cannot decide (unreadable input, a failed import) is blocked: fail closed, and hooks.json sets
onFailure: block so a crash or timeout blocks too. It is a guardrail; the read-only role is the boundary.

    python3 guardia.py [--estado DIR]        # event JSON on stdin
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun  # noqa: E402

SECRETO = re.compile(r"(^|[/\s'\"=])(\.env(\.[\w.-]+)?|\.secretos\.env|\.pgpass|\.netrc|\.git-credentials|"
                     r"id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|[\w.*-]+\.(pem|key|p12|pfx|jks)|credentials(\.json)?|"
                     r"secrets?\.(ya?ml|json|toml|env))($|[/\s'\"])|(^|/)\.(ssh|aws|gnupg|docker|kube)(/|$)", re.I)
BASH_BD = re.compile(r"\b(psql|pg_dump|pg_dumpall|pg_restore|pgcli|createdb|dropdb|createuser|dropuser|vacuumdb|"
                     r"pg_ctl|mysql|mariadb|sqlite3|sqlcmd|mongosh?|redis-cli|clickhouse-client|usql)\b|"
                     r"\b(postgres(ql)?|mysql|mongodb)(\+\w+)?://|\bPG(PASSWORD|HOST|USER|SERVICE)\b|"
                     r"\b(psycopg2?|sqlalchemy|asyncpg|pg8000|sql_lectura)\b|\bdocker\s+(exec|run|compose)\b", re.I)
BASH_CAMBIA = {"rm", "rmdir", "mv", "cp", "dd", "truncate", "chmod", "chown", "ln", "install", "touch", "mkdir",
               "tee", "rsync", "unlink", "shred"}
ESCRITURA = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
# Personal values in a deliverable: emails, phone numbers and Mexican personal tax IDs (RFC). A phone is a run of digit
# groups separated by spaces with at least 9 digits and one 4-digit group ("33 0000 1201", "+1 555 0100 204"), so
# ids ("38 39 40"), dates and amounts do not match.
EMAIL_RFC = re.compile(r"[\w.+*-]*@[\w-]+(\.[\w-]+)*\.[a-z]{2,}\b|\b[A-ZÑ&]{4}\d{6}[A-Z0-9]{3}\b", re.I)  # masked too
TELEFONO = re.compile(r"(?<!\w)\+?\d{1,4}(?: \d{2,4}){2,4}(?!\w)")


def yaml_invalido(texto: str) -> None:
    """A deliverable YAML that does not parse is blocked with the line, so the model fixes it before the client sees
    it (activity 5: Haiku wrote `meaning: Tipo de movimiento: ENT ...` without quotes). Skipped without PyYAML."""
    try:
        import yaml
    except ImportError:
        return
    try:
        yaml.safe_load(texto)
    except yaml.YAMLError as e:
        marca = getattr(e, "problem_mark", None)
        donde = f" at line {marca.line + 1}, column {marca.column + 1}" if marca else ""
        raise Bloqueo(f"auditoria YAML does not parse{donde} ({getattr(e, 'problem', None) or type(e).__name__}). Quote "
                      "values that contain ': ' or '#', then write it again.")


def dato_personal(texto: str) -> bool:
    return bool(EMAIL_RFC.search(texto)) or any(
        sum(c.isdigit() for c in m.group()) >= 9 and re.search(r"\b\d{4}\b", m.group()) for m in TELEFONO.finditer(texto))
LECTURA_RUTA = {"Read": ("file_path",), "NotebookRead": ("notebook_path",), "Grep": ("path", "glob"),
                "Glob": ("path", "pattern")}


class Bloqueo(Exception):
    pass


def dentro_de_auditoria(ruta: str, proyecto: str) -> bool:
    destino = os.path.realpath(os.path.join(proyecto, os.path.expanduser(ruta)))
    return destino.startswith(os.path.join(proyecto, "auditoria") + os.sep)


def revisar_bash(cmd: str, proyecto: str) -> None:
    if BASH_BD.search(cmd):
        raise Bloqueo("Bash against the database is blocked; use the plugin's read-only SQL tools.")
    if SECRETO.search(cmd):
        raise Bloqueo("Reading secrets (.env, keys, credentials) is blocked.")
    for destino in re.findall(r"(?<![0-9&])>>?\s*([^\s;&|]+)", cmd):
        if destino != "/dev/null" and not dentro_de_auditoria(destino, proyecto):
            raise Bloqueo(f"Writing outside auditoria/ is blocked (redirect to {destino}).")
    if re.search(r"\bsed\b[^|;&]*\s-i|\bperl\b[^|;&]*\s-[a-z]*i", cmd):
        raise Bloqueo("In-place edits from Bash are blocked; write deliverables with Write under auditoria/.")
    try:
        partes = shlex.split(cmd, comments=False, posix=True)
    except ValueError:
        raise Bloqueo("Could not parse the Bash command; blocked.")
    for i, p in enumerate(partes):
        if os.path.basename(p) in BASH_CAMBIA and (i == 0 or partes[i - 1] in ("|", ";", "&&", "||", "sudo", "xargs")):
            rutas = [a for a in partes[i + 1:] if not a.startswith("-") and a not in ("|", ";", "&&", "||")]
            fuera = [a for a in rutas if not dentro_de_auditoria(a, proyecto)]
            if fuera or not rutas:
                raise Bloqueo(f"`{os.path.basename(p)}` outside auditoria/ is blocked ({', '.join(fuera) or 'no target'}).")


def decidir(evento: dict, estado_dir: Path) -> None:
    herramienta = evento.get("tool_name") or ""
    entrada = evento.get("tool_input") or {}
    proyecto = os.path.realpath(evento.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())

    agente = comun.agente_del_plugin(evento.get("agent_type"))
    if agente and herramienta not in comun.herramientas_de_agentes()[agente]:
        raise Bloqueo(f"Subagent {agente} may not use {herramienta}; its tools are listed in agents/{agente}.md.")

    if comun.es_herramienta_bd(herramienta):
        if herramienta in comun.HERRAMIENTAS_PROPIAS:
            estado = comun.leer_estado(estado_dir, evento.get("session_id", ""))
            if estado is None:
                raise Bloqueo("The plugin's SessionStart role check did not run in this session; start a new session.")
            if estado.get("lectura_segura") is False:
                raise Bloqueo(f"Database tools are blocked: {estado.get('motivo')}. Configure a read-only role.")
        if comun.corto(herramienta) in comun.SQL_LIBRE:
            try:
                comun.check_read_only(str(entrada.get("sql", "")))
            except ValueError as e:
                raise Bloqueo(f"Only one read-only SELECT is allowed ({e}).")
        return

    if herramienta in ESCRITURA:
        ruta = entrada.get("file_path") or entrada.get("notebook_path") or ""
        if not dentro_de_auditoria(ruta, proyecto):
            raise Bloqueo(f"Writing outside auditoria/ is blocked: {ruta}")
        if SECRETO.search(ruta):
            raise Bloqueo("Writing secret files is blocked.")
        texto = "\n".join(str(x) for x in (entrada.get("content"), entrada.get("new_string"), entrada.get("new_source"),
                                           *[e.get("new_string") for e in entrada.get("edits") or [] if isinstance(e, dict)])
                          if x)
        if dato_personal(texto):
            raise Bloqueo("Personal data in a deliverable is blocked (an email, phone number or tax ID). Name the column "
                          "and give counts or row ids instead of the values.")
        if herramienta == "Write" and ruta.endswith((".yaml", ".yml")):
            yaml_invalido(str(entrada.get("content") or ""))
        return

    for campo in LECTURA_RUTA.get(herramienta, ()):
        if SECRETO.search(str(entrada.get(campo) or "")):
            raise Bloqueo(f"Reading secrets is blocked: {entrada.get(campo)}")

    if herramienta == "Bash":
        revisar_bash(str(entrada.get("command", "")), proyecto)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    estado_dir = comun.dir_estado(argv[argv.index("--estado") + 1] if "--estado" in argv else None)
    try:
        decidir(json.load(sys.stdin), estado_dir)
        return 0
    except Bloqueo as b:
        print(f"legacy-schema-audit: {b}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001  fail closed
        print(f"legacy-schema-audit: guard could not decide ({type(e).__name__}); blocked.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
