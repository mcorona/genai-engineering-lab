"""SessionStart hook of legacy-schema-audit: checks that the configured database role is read-only before the audit.

It connects with the plugin's DSN (CLAUDE_PLUGIN_OPTION_PG_DSN, or LEGACY_AUDIT_DSN for headless and CI runs) and
fails the check if the role is a superuser, can create roles or databases, bypasses row security, replicates, can
create objects in the audited schema, or holds INSERT, UPDATE, DELETE or TRUNCATE on any table of the database.
The result is saved per session for the PreToolUse guard, which blocks the bundled database tools when the role can
write (or when this check did not run), and it is added to Claude's context. Without a DSN the audit goes through a
remote MCP server, whose own permissions apply. Never prints the DSN. Always exits 0 (SessionStart cannot block).

    python3 verificar_rol.py [--estado DIR]        # event JSON on stdin
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun  # noqa: E402

CONSULTA = """
SELECT current_user,
       r.rolsuper, r.rolcreaterole, r.rolcreatedb, r.rolbypassrls, r.rolreplication,
       has_schema_privilege(current_user, %(esquema)s, 'CREATE'),
       (SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind IN ('r', 'p') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
           AND n.nspname NOT LIKE 'pg_toast%%'
           AND has_table_privilege(current_user, c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE')),
       (SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = %(esquema)s AND c.relkind IN ('r', 'v', 'm', 'p'))
FROM pg_roles r WHERE r.rolname = current_user
"""
ATRIBUTOS = ("superuser", "createrole", "createdb", "bypassrls", "replication")


def evaluar(dsn: str, esquema: str) -> dict:
    if not dsn:
        return {"modo": "remoto", "lectura_segura": None,
                "motivo": "no DSN configured: the audit must use a remote MCP server, whose permissions apply"}
    try:
        import psycopg
        with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as c:
            fila = c.execute(CONSULTA, {"esquema": esquema}).fetchone()
    except Exception as e:  # noqa: BLE001
        return {"modo": "dsn", "lectura_segura": False,
                "motivo": f"could not verify the role ({type(e).__name__}: {str(e).splitlines()[0][:160]})"}
    rol, *banderas, crear, escribibles, objetos = fila
    problemas = [a for a, v in zip(ATRIBUTOS, banderas) if v]
    if crear:
        problemas.append(f"CREATE on schema {esquema}")
    if escribibles:
        problemas.append(f"write grants on {escribibles} table(s)")
    if objetos == 0:
        return {"modo": "dsn", "rol": rol, "lectura_segura": False,
                "motivo": f"role {rol} sees no objects in schema {esquema}"}
    if problemas:
        return {"modo": "dsn", "rol": rol, "lectura_segura": False,
                "motivo": f"role {rol} can write ({', '.join(problemas)})"}
    return {"modo": "dsn", "rol": rol, "lectura_segura": True, "objetos": objetos,
            "motivo": f"role {rol} is read-only and sees {objetos} objects in schema {esquema}"}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    estado_dir = comun.dir_estado(argv[argv.index("--estado") + 1] if "--estado" in argv else None)
    try:
        evento = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        evento = {}
    esquema = comun.esquema_configurado()
    estado = evaluar(comun.dsn_configurado(), esquema)
    try:
        comun.escribir_estado(estado_dir, evento.get("session_id", ""), estado)
    except OSError as e:
        estado["motivo"] += f"; state not saved ({type(e).__name__}), database tools will be blocked"
    if estado["lectura_segura"] is False:
        texto = (f"legacy-schema-audit: STOP. {estado['motivo']}. The plugin's database tools are blocked in this "
                 f"session; ask the user for a read-only role before auditing.")
    elif estado["lectura_segura"]:
        texto = f"legacy-schema-audit: {estado['motivo']}. Database tools enabled."
    else:
        texto = f"legacy-schema-audit: {estado['motivo']}."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": texto}},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
