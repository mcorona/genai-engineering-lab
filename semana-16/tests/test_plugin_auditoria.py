"""Plugin legacy-schema-audit (actividad 3): estructura, validate --strict, guardia SQL y servidor MCP de solo lectura."""
import asyncio
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / "legacy-schema-audit"
_spec = importlib.util.spec_from_file_location("sql_lectura", PLUGIN / "servidor" / "sql_lectura.py")
srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srv)

DSN = os.environ.get("PG_DSN") or os.environ.get("PG_ADMIN_DSN")
ADMIN = os.environ.get("PG_ADMIN_DSN")
OBJETOS = {"almmst", "artmst", "artnot", "exidet", "movinv", "ocpcab", "prvcto", "prvmst", "vtadia"}
con_base = pytest.mark.skipif(not DSN, reason="sin base (PG_DSN)")


def frontmatter(p: Path) -> dict:
    texto = p.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", texto, re.S)
    assert m, p
    return dict(re.findall(r"^([\w-]+):\s*(.*)$", m.group(1), re.M))


# ---------- estructura ----------

def test_manifiesto_con_userconfig_sensible():
    m = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert m["name"] == "legacy-schema-audit" and not m["name"].startswith(("claude", "anthropic"))
    assert m["userConfig"]["pg_dsn"]["sensitive"] is True
    assert m["userConfig"]["audit_schema"]["default"] == "legado" and not m["userConfig"]["audit_schema"].get("sensitive")


def test_mcp_usa_userconfig_y_ruta_del_plugin():
    s = json.loads((PLUGIN / ".mcp.json").read_text())["mcpServers"]["legacy-sql"]
    assert s["args"] == ["${CLAUDE_PLUGIN_ROOT}/servidor/sql_lectura.py"]
    assert s["env"] == {"PG_DSN": "${user_config.pg_dsn}", "AUDIT_SCHEMA": "${user_config.audit_schema}"}
    assert not (PLUGIN / "bin").exists()  # bin/ bloquea la distribución por claude.ai y Cowork (actividad 1)


def test_skill_y_comandos():
    f = frontmatter(PLUGIN / "skills" / "auditar" / "SKILL.md")
    assert f["name"] == "auditar" and "legacy database schema" in f["description"]
    texto = (PLUGIN / "skills" / "auditar" / "SKILL.md").read_text(encoding="utf-8")
    for salida in ("auditoria/diccionario.yaml", "auditoria/relaciones.mmd", "auditoria/riesgos.md", "auditoria/resumen.md"):
        assert salida in texto
    for cat in ("datos_personales", "huerfanos", "duplicados", "nulos_en_clave", "unidades_inconsistentes",
                "reglas_fuera_de_la_base", "instrucciones_inyectadas"):
        assert f"`{cat}`" in texto, cat
    for nombre, modo in (("auditoria-completa", "completa"), ("solo-diccionario", "diccionario"), ("solo-riesgos", "riesgos")):
        f = frontmatter(PLUGIN / "skills" / nombre / "SKILL.md")
        cuerpo = (PLUGIN / "skills" / nombre / "SKILL.md").read_text(encoding="utf-8")
        assert f["disable-model-invocation"] == "true" and f"`{modo}`" in cuerpo and "$ARGUMENTS" in cuerpo


@pytest.mark.skipif(not shutil.which("claude"), reason="sin Claude Code")
def test_validate_strict_limpio():
    p = subprocess.run(["claude", "plugin", "validate", "--strict", str(PLUGIN)], capture_output=True, text=True,
                       timeout=120)
    salida = p.stdout + p.stderr
    assert p.returncode == 0 and "Validation passed" in salida and "‼" not in salida and "warning" not in salida.lower(), salida


# ---------- guardia (sin base) ----------

PERMITIDAS = ["SELECT mov_id FROM movinv WHERE mov_art IS NULL",
              "SELECT a.art_cd FROM legado.artmst a JOIN prvmst p ON p.prv_id = a.art_prv",
              "WITH x AS (SELECT exi_art, SUM(exi_qty) q FROM exidet GROUP BY 1) SELECT * FROM x",
              "SELECT mov_art FROM movinv GROUP BY 1 HAVING COUNT(DISTINCT mov_uni) > 1 UNION SELECT 'x'"]
BLOQUEADAS = [("DELETE FROM movinv", "write_blocked"), ("UPDATE artmst SET art_cst = 0", "write_blocked"),
              ("DROP TABLE movinv", "write_blocked"), ("SELECT * INTO copia FROM movinv", "write_blocked"),
              ("SELECT 1; DELETE FROM movinv", "multiple_statements"),
              ("SELECT pg_read_file('/etc/passwd')", "forbidden_function"),
              ("SELECT lo_import('/etc/passwd')", "forbidden_function"),
              ("SELECT set_config('search_path', 'public', false)", "forbidden_function"),
              ("SELECT * FROM public.products", "out_of_scope"), ("SELECT * FROM pg_catalog.pg_authid", "out_of_scope"),
              ("SELECT * FROM products", "unknown_object"), ("COPY movinv TO STDOUT", "write_blocked")]


@pytest.mark.parametrize("sql", PERMITIDAS)
def test_guardia_permite(sql):
    assert srv.guard(sql, "legado", OBJETOS)


@pytest.mark.parametrize("sql,tipo", BLOQUEADAS)
def test_guardia_bloquea(sql, tipo):
    with pytest.raises(srv.ToolError) as e:
        srv.guard(sql, "legado", OBJETOS)
    assert e.value.kind == tipo


def test_sin_dsn_error_claro():
    r = srv.call(srv.Database("", "legado"), "list_objects", {})
    assert not r["ok"] and r["error"]["type"] == "no_dsn"


def test_esquema_invalido():
    with pytest.raises(srv.ToolError):
        srv.Database("x", "legado; DROP SCHEMA x")


# ---------- con base ----------

@con_base
def test_herramientas_contra_la_base():
    db = srv.Database(DSN, "legado")
    objs = srv.call(db, "list_objects", {})
    assert objs["ok"] and {o["name"] for o in objs["objects"]} == OBJETOS
    d = srv.call(db, "describe_object", {"name": "legado.movinv"})
    assert d["ok"] and [c["type"] for c in d["declared_constraints"]] == ["primary key"]
    assert srv.call(db, "describe_object", {"name": "artmst"})["note"]  # las vistas no declaran llaves
    p = srv.call(db, "profile_table", {"name": "prvcto", "top": 2})
    assert p["ok"] and p["rows"] == 15 and next(c for c in p["columns"] if c["column"] == "cto_prv")["nulls"] == 1
    r = srv.call(db, "run_select", {"sql": "SELECT mov_id FROM movinv WHERE mov_art IS NULL OR mov_alm IS NULL ORDER BY 1"})
    assert r["ok"] and r["rows"] == [[42], [43], [44]]
    assert srv.call(db, "run_select", {"sql": "SELECT art_cd FROM artmst", "max_rows": 5})["truncated"]


@pytest.mark.skipif(not ADMIN, reason="sin PG_ADMIN_DSN")
def test_transaccion_de_solo_lectura_aun_con_rol_administrador():
    """Si la guardia fallara, la transacción READ ONLY sigue impidiendo escribir (segunda capa)."""
    db = srv.Database(ADMIN, "legado")
    with pytest.raises(srv.ToolError) as e:
        db.query("INSERT INTO movinv (mov_id) VALUES (999)")
    assert "read-only" in e.value.message
    assert db.query("SELECT COUNT(*) FROM movinv")[1] == [(44,)]


@con_base
def test_protocolo_mcp_por_stdio():
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def sesion():
        params = StdioServerParameters(command=sys.executable, args=[str(PLUGIN / "servidor" / "sql_lectura.py")],
                                       env={**os.environ, "PG_DSN": DSN, "AUDIT_SCHEMA": "legado"})
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            nombres = [t.name for t in (await s.list_tools()).tools]
            ok = await s.call_tool("run_select", {"sql": "SELECT COUNT(*) FROM prvcto"})
            mal = await s.call_tool("run_select", {"sql": "DELETE FROM prvcto"})
            return nombres, ok, mal

    nombres, ok, mal = asyncio.run(sesion())
    assert nombres == ["list_objects", "describe_object", "profile_table", "run_select"]
    assert not ok.is_error and json.loads(ok.content[0].text)["rows"] == [[15]]
    assert mal.is_error and json.loads(mal.content[0].text)["error"]["type"] == "write_blocked"


@pytest.mark.parametrize("env,esperado", [
    ({"PG_DSN": "postgresql://a", "AUDIT_SCHEMA": "ventas", "LEGACY_AUDIT_DSN": "postgresql://b"}, ("postgresql://a", "ventas")),
    ({"PG_DSN": "", "AUDIT_SCHEMA": "legado", "LEGACY_AUDIT_DSN": "postgresql://b"}, ("postgresql://b", "legado")),
    ({"PG_DSN": "${user_config.pg_dsn}", "AUDIT_SCHEMA": "${user_config.audit_schema}"}, ("", "legado")),
])
def test_configuracion_desde_el_entorno(env, esperado):
    assert srv.config_from_env(env) == esperado
