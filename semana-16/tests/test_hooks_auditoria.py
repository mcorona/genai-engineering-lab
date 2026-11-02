"""Hooks y subagentes de legacy-schema-audit (actividad 4), sin API: entradas guionadas a cada hook (permite / bloquea,
códigos de salida, bitácora válida) y la lista de herramientas de cada subagente aplicada por la guardia."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / "legacy-schema-audit"
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))
import comun  # noqa: E402

P = "mcp__plugin_legacy-schema-audit_legacy-sql__"
R = "mcp__legado-remoto__"
DSN = os.environ.get("PG_DSN")
ADMIN = os.environ.get("PG_ADMIN_DSN")


def correr(script: str, evento, estado: Path, env=None) -> subprocess.CompletedProcess:
    entrada = evento if isinstance(evento, str) else json.dumps(evento)
    return subprocess.run([sys.executable, str(SCRIPTS / script), "--estado", str(estado)] if script != "bitacora.py"
                          else [sys.executable, str(SCRIPTS / script)], input=entrada, capture_output=True, text=True,
                          timeout=30, env={**os.environ, **(env or {})})


@pytest.fixture
def proyecto(tmp_path):
    (tmp_path / "proyecto").mkdir()
    return tmp_path / "proyecto"


@pytest.fixture
def estado(tmp_path):
    """Estado de sesión como lo deja SessionStart con un rol de solo lectura (sesión 'segura')."""
    d = tmp_path / "estado"
    comun.escribir_estado(d, "segura", {"modo": "dsn", "lectura_segura": True, "motivo": "role x is read-only"})
    comun.escribir_estado(d, "insegura", {"modo": "dsn", "lectura_segura": False, "motivo": "role admin can write"})
    return d


def ev(herramienta, entrada, proyecto, sesion="segura", **extra):
    return {"session_id": sesion, "cwd": str(proyecto), "hook_event_name": "PreToolUse", "tool_name": herramienta,
            "tool_input": entrada, **extra}


# ---------- PreToolUse: guardia ----------

PERMITE = [
    (P + "run_select", {"sql": "SELECT mov_id FROM movinv WHERE mov_art IS NULL"}),
    (P + "run_select", {"sql": "WITH x AS (SELECT 1 AS n) SELECT n FROM x"}),
    (P + "profile_table", {"name": "prvcto"}),
    (R + "ejecutar_sql", {"sql": "SELECT COUNT(*) FROM artmst"}),
    ("Write", {"file_path": "auditoria/riesgos.md", "content": "x"}),
    ("Edit", {"file_path": "{p}/auditoria/diccionario.yaml", "old_string": "a", "new_string": "b"}),
    ("Read", {"file_path": "auditoria/bitacora.jsonl"}),
    ("Bash", {"command": "ls -la auditoria"}),
    ("Bash", {"command": "mkdir -p auditoria/anexos"}),
    ("Bash", {"command": "echo listo > auditoria/nota.txt 2>&1"}),
    ("Skill", {"skill": "legacy-schema-audit:auditar"}),
    ("Grep", {"pattern": "R-0", "path": "auditoria"}),
]
BLOQUEA = [
    (P + "run_select", {"sql": "DELETE FROM movinv"}, "read-only SELECT"),
    (P + "run_select", {"sql": "SELECT 1; DROP TABLE movinv"}, "read-only SELECT"),
    (P + "run_select", {"sql": "SELECT pg_read_file('/etc/passwd')"}, "read-only SELECT"),
    (R + "ejecutar_sql", {"sql": "UPDATE artmst SET art_cst = 0"}, "read-only SELECT"),
    (R + "validar_sql", {"sql": "INSERT INTO artnot VALUES (99, 'x', 'y', now())"}, "read-only SELECT"),
    ("Bash", {"command": "psql \"$PG_ADMIN_DSN\" -c 'select 1'"}, "against the database"),
    ("Bash", {"command": "PGPASSWORD=x pg_dump -h localhost inventory > auditoria/dump.sql"}, "against the database"),
    ("Bash", {"command": "python3 -c \"import psycopg; psycopg.connect('postgresql://a@b/c')\""}, "against the database"),
    ("Bash", {"command": "docker exec -i copilot-db psql -U postgres"}, "against the database"),
    ("Read", {"file_path": "{p}/.env"}, "secrets"),
    ("Read", {"file_path": "/Users/x/AI-projects-llm-internals/semana-14/auth/.secretos.env"}, "secrets"),
    ("Read", {"file_path": "/home/x/.ssh/id_ed25519"}, "secrets"),
    ("Read", {"file_path": "/home/x/.aws/credentials"}, "secrets"),
    ("Grep", {"pattern": "PASSWORD", "path": ".env.local"}, "secrets"),
    ("Glob", {"pattern": "**/*.pem"}, "secrets"),
    ("Bash", {"command": "cat .env"}, "secrets"),
    ("Bash", {"command": "grep -r DSN ~/.pgpass"}, "secrets"),
    ("Write", {"file_path": "notas.txt", "content": "x"}, "outside auditoria/"),
    ("Write", {"file_path": "/tmp/fuga.txt", "content": "x"}, "outside auditoria/"),
    ("Edit", {"file_path": "auditoria/../README.md", "old_string": "a", "new_string": "b"}, "outside auditoria/"),
    ("MultiEdit", {"file_path": "../otro/x.py", "edits": []}, "outside auditoria/"),
    ("NotebookEdit", {"notebook_path": "nb.ipynb", "new_source": "x"}, "outside auditoria/"),
    ("Bash", {"command": "echo x > notas.txt"}, "outside auditoria/"),
    ("Bash", {"command": "echo x >> ../fuera.log"}, "outside auditoria/"),
    ("Bash", {"command": "rm -rf build"}, "outside auditoria/"),
    ("Bash", {"command": "cp auditoria/riesgos.md /tmp/"}, "outside auditoria/"),
    ("Bash", {"command": "sed -i 's/a/b/' README.md"}, "In-place"),
]


def _rellenar(entrada, proyecto):
    return {k: (v.replace("{p}", str(proyecto)) if isinstance(v, str) else v) for k, v in entrada.items()}


@pytest.mark.parametrize("herramienta,entrada", PERMITE, ids=[f"{h}:{list(e.values())[0]}"[:60] for h, e in PERMITE])
def test_guardia_permite(herramienta, entrada, proyecto, estado):
    p = correr("guardia.py", ev(herramienta, _rellenar(entrada, proyecto), proyecto), estado)
    assert p.returncode == 0 and p.stderr == "", p.stderr


@pytest.mark.parametrize("herramienta,entrada,motivo", BLOQUEA, ids=[f"{h}:{list(e.values())[0]}"[:60] for h, e, _ in BLOQUEA])
def test_guardia_bloquea_con_exit_2(herramienta, entrada, motivo, proyecto, estado):
    p = correr("guardia.py", ev(herramienta, _rellenar(entrada, proyecto), proyecto), estado)
    assert p.returncode == 2 and p.stderr.startswith("legacy-schema-audit:") and motivo in p.stderr, p.stderr


def test_guardia_bloquea_herramientas_de_bd_si_el_rol_puede_escribir(proyecto, estado):
    p = correr("guardia.py", ev(P + "run_select", {"sql": "SELECT 1"}, proyecto, sesion="insegura"), estado)
    assert p.returncode == 2 and "role admin can write" in p.stderr


def test_guardia_bloquea_si_sessionstart_no_corrio(proyecto, estado):
    p = correr("guardia.py", ev(P + "list_objects", {}, proyecto, sesion="desconocida"), estado)
    assert p.returncode == 2 and "SessionStart" in p.stderr


def test_guardia_remota_no_depende_del_estado(proyecto, estado):
    """El servidor remoto aplica sus propios permisos (OAuth): sin DSN no hay rol que verificar aquí."""
    p = correr("guardia.py", ev(R + "describir_esquema", {}, proyecto, sesion="desconocida"), estado)
    assert p.returncode == 0


@pytest.mark.parametrize("entrada", ["no es json", "", json.dumps({"tool_name": 5, "tool_input": "x"})])
def test_guardia_falla_cerrada(entrada, estado):
    p = correr("guardia.py", entrada, estado)
    assert p.returncode == 2 and "blocked" in p.stderr


# ---------- subagentes: herramientas mínimas ----------

AGENTES = comun.herramientas_de_agentes()
PROHIBIDAS_A_TODOS = {"Bash", "Write", "Edit", "MultiEdit", "NotebookEdit", "Read", "Grep", "Glob", "WebFetch",
                      "WebSearch", "Agent", "Task"}


def test_subagentes_y_listas_minimas():
    assert set(AGENTES) == {"perfilador", "analista-relaciones", "revisor-riesgos"}
    nombres_servidor = {P + n for n in ("list_objects", "describe_object", "profile_table", "run_select")}
    for agente, tools in AGENTES.items():
        assert not tools & PROHIBIDAS_A_TODOS, agente
        propias = {t for t in tools if t.startswith(P)}
        assert propias <= nombres_servidor and propias, agente
    assert P + "run_select" not in AGENTES["perfilador"]          # estadísticas, sin SQL libre
    assert P + "profile_table" not in AGENTES["analista-relaciones"]
    assert P + "run_select" in AGENTES["revisor-riesgos"] and P + "run_select" in AGENTES["analista-relaciones"]


def test_subagentes_sin_campos_que_claude_code_ignora():
    for f in (PLUGIN / "agents").glob("*.md"):
        cabecera = f.read_text(encoding="utf-8").split("---")[1]
        assert not re.search(r"^(hooks|mcpServers|permissionMode):", cabecera, re.M), f.name
        assert re.search(r"^model: (haiku|sonnet)$", cabecera, re.M), f.name


@pytest.mark.parametrize("agente,herramienta,permitido", [
    ("legacy-schema-audit:perfilador", P + "profile_table", True),
    ("legacy-schema-audit:perfilador", P + "run_select", False),
    ("legacy-schema-audit:perfilador", "Write", False),
    ("legacy-schema-audit:perfilador", "Bash", False),
    ("legacy-schema-audit:analista-relaciones", P + "run_select", True),
    ("legacy-schema-audit:analista-relaciones", P + "profile_table", False),
    ("legacy-schema-audit:analista-relaciones", "Read", False),
    ("legacy-schema-audit:revisor-riesgos", P + "run_select", True),
    ("legacy-schema-audit:revisor-riesgos", R + "ejecutar_sql", True),
    ("legacy-schema-audit:revisor-riesgos", "Write", False),
    ("legacy-schema-audit:revisor-riesgos", "mcp__otro-servidor__borrar", False),
    ("general-purpose", P + "run_select", True),     # no es del plugin: aplica solo el resto de la guardia
])
def test_subagente_no_usa_herramientas_fuera_de_su_lista(agente, herramienta, permitido, proyecto, estado):
    entrada = {"sql": "SELECT 1"} if herramienta.endswith(("run_select", "ejecutar_sql")) else \
        {"file_path": "auditoria/x.md", "content": "x"} if herramienta == "Write" else \
        {"command": "ls auditoria"} if herramienta == "Bash" else {"file_path": "auditoria/x"} if herramienta == "Read" \
        else {"name": "movinv"}
    p = correr("guardia.py", ev(herramienta, entrada, proyecto, agent_type=agente, agent_id="a-1"), estado)
    assert (p.returncode == 0) == permitido, p.stderr
    if not permitido:
        assert "may not use" in p.stderr


def test_skill_orquesta_los_tres_subagentes():
    texto = (PLUGIN / "skills" / "auditar" / "SKILL.md").read_text(encoding="utf-8")
    for a in AGENTES:
        assert f"legacy-schema-audit:{a}" in texto
    assert "in parallel" in texto and "auditoria/bitacora.jsonl" in texto


# ---------- PostToolUse: bitácora ----------

def post(herramienta, entrada, respuesta, proyecto, **extra):
    return {"session_id": "s", "cwd": str(proyecto), "hook_event_name": "PostToolUse", "tool_name": herramienta,
            "tool_input": entrada, "tool_response": respuesta, **extra}


OK = {"ok": True, "columns": ["mov_id"], "total_rows": 2, "rows": [[35], [36]], "truncated": False,
      "sql": "SELECT mov_id FROM movinv"}


@pytest.mark.parametrize("forma", ["dict", "contenido_mcp", "texto"])
def test_bitacora_jsonl_valida_sin_filas(forma, proyecto):
    respuesta = {"dict": OK, "contenido_mcp": {"content": [{"type": "text", "text": json.dumps(OK)}], "isError": False},
                 "texto": json.dumps(OK)}[forma]
    p = correr("bitacora.py", post(P + "run_select", {"sql": "SELECT mov_id FROM movinv WHERE x", "max_rows": 10},
                                   respuesta, proyecto, agent_type="legacy-schema-audit:revisor-riesgos"), None)
    assert p.returncode == 0, p.stderr
    lineas = (proyecto / "auditoria" / "bitacora.jsonl").read_text().splitlines()
    assert len(lineas) == 1
    e = json.loads(lineas[0])
    assert e["tool"] == "run_select" and e["server"] == "legacy-sql" and e["sql"] == "SELECT mov_id FROM movinv WHERE x"
    assert e["ok"] is True and e["rows"] == 2 and e["truncated"] is False and e["error"] is None
    assert e["agent"] == "legacy-schema-audit:revisor-riesgos" and e["args"] == {"max_rows": 10}
    assert "35" not in lineas[0]  # nunca las filas


def test_bitacora_registra_errores_y_remotas(proyecto):
    correr("bitacora.py", post(P + "run_select", {"sql": "DELETE FROM x"},
                               {"ok": False, "error": {"type": "write_blocked", "message": "..."}}, proyecto), None)
    correr("bitacora.py", post(R + "ejecutar_sql", {"sql": "SELECT 1"},
                               {"ok": True, "total_filas": 1, "truncado": False}, proyecto), None)
    correr("bitacora.py", post(P + "profile_table", {"name": "prvcto"}, {"ok": True, "rows": 15}, proyecto), None)
    e = [json.loads(x) for x in (proyecto / "auditoria" / "bitacora.jsonl").read_text().splitlines()]
    assert [(x["tool"], x["ok"], x["error"], x["rows"]) for x in e] == [
        ("run_select", False, "write_blocked", None), ("ejecutar_sql", True, None, 1), ("profile_table", True, None, 15)]
    assert e[1]["server"] == "remote" and e[2]["sql"] is None and e[2]["args"] == {"name": "prvcto"}


def test_bitacora_ignora_otras_herramientas_y_nunca_bloquea(proyecto):
    assert correr("bitacora.py", post("mcp__otro__x", {}, {}, proyecto), None).returncode == 0
    assert not (proyecto / "auditoria" / "bitacora.jsonl").exists()
    assert correr("bitacora.py", "basura", None).returncode == 0


# ---------- SessionStart: rol de solo lectura ----------

def sesion(estado, sid, env):
    p = correr("verificar_rol.py", {"session_id": sid, "hook_event_name": "SessionStart", "source": "startup"}, estado,
               env={"CLAUDE_PLUGIN_OPTION_PG_DSN": "", **env})
    salida = json.loads(p.stdout)["hookSpecificOutput"]
    return p.returncode, salida, comun.leer_estado(estado, sid)


def test_sessionstart_sin_dsn_modo_remoto(tmp_path):
    env = {k: "" for k in ("LEGACY_AUDIT_DSN",)}
    codigo, salida, est = sesion(tmp_path, "r", env)
    assert codigo == 0 and salida["hookEventName"] == "SessionStart" and est["modo"] == "remoto"
    assert est["lectura_segura"] is None


def test_sessionstart_base_inalcanzable_bloquea(tmp_path):
    codigo, salida, est = sesion(tmp_path, "x", {"LEGACY_AUDIT_DSN": "postgresql://nadie:nada@127.0.0.1:1/x"})
    assert codigo == 0 and est["lectura_segura"] is False and "STOP" in salida["additionalContext"]
    assert "nada@" not in salida["additionalContext"]  # el DSN nunca se imprime


@pytest.mark.skipif(not (DSN or ADMIN), reason="sin PG_DSN ni PG_ADMIN_DSN")
def test_sessionstart_rol_de_solo_lectura(tmp_path):
    """Con PG_DSN (copilot_ro en CI) o, si no hay, con un rol de solo lectura creado para la prueba."""
    import psycopg
    from psycopg.conninfo import make_conninfo
    dsn, temporal = DSN, False
    if not dsn:
        with psycopg.connect(ADMIN, autocommit=True) as c:
            c.execute("DROP ROLE IF EXISTS lsa_prueba_ro")
            c.execute("CREATE ROLE lsa_prueba_ro LOGIN PASSWORD 'prueba-ro'")
            c.execute("GRANT USAGE ON SCHEMA legado TO lsa_prueba_ro")
            c.execute("GRANT SELECT ON ALL TABLES IN SCHEMA legado TO lsa_prueba_ro")
        dsn, temporal = make_conninfo(ADMIN, user="lsa_prueba_ro", password="prueba-ro"), True
    try:
        codigo, salida, est = sesion(tmp_path, "ro", {"LEGACY_AUDIT_DSN": dsn})
        assert codigo == 0 and est["lectura_segura"] is True and "Database tools enabled" in salida["additionalContext"]
    finally:
        if temporal:
            with psycopg.connect(ADMIN, autocommit=True) as c:
                c.execute("REVOKE ALL ON ALL TABLES IN SCHEMA legado FROM lsa_prueba_ro")
                c.execute("REVOKE USAGE ON SCHEMA legado FROM lsa_prueba_ro")
                c.execute("DROP ROLE lsa_prueba_ro")


@pytest.mark.skipif(not ADMIN, reason="sin PG_ADMIN_DSN")
def test_sessionstart_rol_administrador_bloquea_y_la_guardia_lo_aplica(tmp_path, proyecto):
    codigo, salida, est = sesion(tmp_path, "adm", {"LEGACY_AUDIT_DSN": ADMIN})
    assert codigo == 0 and est["lectura_segura"] is False and "can write" in est["motivo"]
    assert "STOP" in salida["additionalContext"]
    p = correr("guardia.py", ev(P + "run_select", {"sql": "SELECT 1"}, proyecto, sesion="adm"), tmp_path)
    assert p.returncode == 2 and "can write" in p.stderr


@pytest.mark.skipif(not ADMIN, reason="sin PG_ADMIN_DSN")
def test_sessionstart_detecta_un_grant_de_escritura(tmp_path):
    import psycopg
    from psycopg.conninfo import make_conninfo
    with psycopg.connect(ADMIN, autocommit=True) as c:
        c.execute("DROP ROLE IF EXISTS lsa_prueba_rw")
        c.execute("CREATE ROLE lsa_prueba_rw LOGIN PASSWORD 'prueba-rw'")
        c.execute("GRANT USAGE ON SCHEMA legado TO lsa_prueba_rw")
        c.execute("GRANT SELECT ON ALL TABLES IN SCHEMA legado TO lsa_prueba_rw")
        c.execute("GRANT INSERT ON legado.movinv TO lsa_prueba_rw")
    try:
        _, _, est = sesion(tmp_path, "rw", {"LEGACY_AUDIT_DSN": make_conninfo(ADMIN, user="lsa_prueba_rw",
                                                                             password="prueba-rw")})
        assert est["lectura_segura"] is False and "write grants on 1 table" in est["motivo"]
    finally:
        with psycopg.connect(ADMIN, autocommit=True) as c:
            c.execute("REVOKE ALL ON ALL TABLES IN SCHEMA legado FROM lsa_prueba_rw")
            c.execute("REVOKE USAGE ON SCHEMA legado FROM lsa_prueba_rw")
            c.execute("DROP ROLE lsa_prueba_rw")


# ---------- hooks.json ----------

def test_hooks_json_exec_y_falla_cerrada():
    h = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]
    assert set(h) == {"SessionStart", "PreToolUse", "PostToolUse"}
    pre = h["PreToolUse"][0]
    assert pre["matcher"] == "*" and pre["hooks"][0]["onFailure"] == "block"
    for evento in h.values():
        for grupo in evento:
            for k in grupo["hooks"]:
                assert k["command"] == "python3" and k["args"][0].startswith("${CLAUDE_PLUGIN_ROOT}/scripts/")
                assert (SCRIPTS / Path(k["args"][0]).name).exists()
    assert h["PostToolUse"][0]["matcher"] == "mcp__.*"
