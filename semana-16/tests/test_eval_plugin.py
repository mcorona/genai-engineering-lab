"""Actividad 5: suite de `claude plugin eval` (estructura, sin llamar al modelo) y evaluador propio de calidad."""
import builtins
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest

S16 = Path(__file__).resolve().parents[1]
EVALS = S16 / "legacy-schema-audit" / "evals"
DSN = os.environ.get("PG_ADMIN_DSN") or os.environ.get("PG_DSN")


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


gen = cargar("generar_casos", S16 / "eval" / "generar_casos.py")
cal = cargar("calidad", S16 / "eval" / "calidad.py")


def frontmatter(p: Path) -> dict:
    import yaml
    return yaml.safe_load(p.read_text(encoding="utf-8").split("---")[1]) or {}


# ---------- suite de plugin eval ----------

def test_suite_igual_al_generador(tmp_path, monkeypatch):
    monkeypatch.setattr(gen, "EVALS", tmp_path)
    gen.escribir()
    for f in tmp_path.rglob("*.md"):
        assert f.read_text() == (EVALS / f.relative_to(tmp_path)).read_text(), f"{f.relative_to(tmp_path)}: regenera"


def test_casos_es_en_positivos_y_negativos():
    casos = sorted(d for d in EVALS.iterdir() if (d / "prompt.md").exists())
    assert 8 <= len(casos) <= 12
    tags = {c: gen.CASOS[c.name]["tags"] for c in casos}
    assert sum("negativo" in t for t in tags.values()) >= 3
    assert {"es", "en"} <= {x for t in tags.values() for x in t}
    llm = 0
    for c in casos:
        graders = {g.stem: frontmatter(g) for g in (c / "graders").glob("*.md")}
        assert any(g["type"] != "tool_used" for g in graders.values()), f"{c.name}: sin grader de resultado"
        llm += sum(g["type"] == "llm" for g in graders.values())
        p = frontmatter(c / "prompt.md")
        assert p["runs"] >= 3 and p["max_turns"] and p["timeout_seconds"]
        for g in graders.values():   # las herramientas siguen a los graders
            if g["type"] in ("file_exists",) and g.get("exists", True):
                assert "Write" in p["allowed_tools"], c.name
        if "negativo" in tags[c]:
            assert any(g["type"] == "tool_used" and g.get("max") == 0 and g.get("arm") == "both" for g in graders.values())
    assert 1 <= llm <= 4


def test_graders_bien_formados():
    tipos = {"regex", "file_exists", "tool_used", "tool_order", "llm", "baseline"}
    for g in EVALS.glob("*/graders/*.md"):
        fm, cuerpo = frontmatter(g), g.read_text().split("---", 2)[2].strip()
        assert fm["type"] in tipos, g
        if fm["type"] == "regex":
            assert not cuerpo.startswith("(?"), f"{g}: JavaScript RegExp usa flags:"
            re.compile(cuerpo)
        if fm["type"] == "tool_used" and "input_match" in fm:
            assert "(?" not in fm["input_match"]
        if fm["type"] == "llm":
            assert "PASS" in cuerpo and "FAIL" in cuerpo


def test_mock_del_servidor():
    fm = frontmatter(EVALS / "mocks" / "legacy-sql" / "_server.md")
    assert fm["type"] == "agent" and set(fm["tools"]) == {"list_objects", "describe_object", "profile_table", "run_select"}
    assert "DELETE" in fm["abort_when"]
    herramientas = json.loads((EVALS / "mocks" / "legacy-sql" / "_tools.json").read_text())["tools"]
    assert [t["name"] for t in herramientas] == fm["tools"]


def test_guardia_sin_sqlglot_usa_regex_estricta(monkeypatch):
    sys.path.insert(0, str(S16 / "legacy-schema-audit" / "scripts"))
    import comun
    real = builtins.__import__

    def sin_sqlglot(nombre, *a, **k):
        if nombre.startswith("sqlglot"):
            raise ImportError("sin sqlglot")
        return real(nombre, *a, **k)

    monkeypatch.setattr(builtins, "__import__", sin_sqlglot)
    comun.check_read_only("SELECT * FROM t WHERE c = 'DELETE'")
    comun.check_read_only("WITH x AS (SELECT 1) SELECT * FROM x")
    for q in ("DELETE FROM t", "SELECT 1; DROP TABLE t", "SELECT pg_read_file('x')", "SELECT * INTO z FROM t"):
        with pytest.raises(ValueError):
            comun.check_read_only(q)


# ---------- evaluador propio ----------

def test_conceptos_cubren_la_verdad():
    verdad = {f"{x['tabla']}.{x['columna']}" for x in json.loads((S16 / "verdad" / "diccionario.json").read_text())}
    assert set(cal.CONCEPTOS) == verdad


def test_yaml_flexible_y_llaves():
    plugin = {"tables": [{"name": "movinv", "columns": [{"name": "mov_art", "foreign_key": "artmst.art_cd",
                                                          "meaning": "Item code", "personal_data": False}]}]}
    otro = {"movinv": {"columns": {"mov_art": {"description": "Article", "references": "artmst(art_cd)"},
                                   "mov_usr": {"description": "User login", "pii": "yes"}}}}
    a, b = cal.columnas_del_yaml(plugin), cal.columnas_del_yaml(otro)
    assert set(a) == {"movinv.mov_art"} and set(b) == {"movinv.mov_art", "movinv.mov_usr"}
    tabla_de = {"art_cd": "artmst"}
    assert cal._fk("artmst(art_cd)", tabla_de) == cal._fk("legado.artmst.art_cd", tabla_de) == "artmst.art_cd"
    assert cal._fk({"table": "artmst", "column": "art_cd"}, tabla_de) == "artmst.art_cd"
    assert cal._bool(cal._campo(b["movinv.mov_usr"], "pii"))


def test_hallazgos_sin_nombres_del_plugin():
    md = "## Orphan orders in movinv\n```sql\nSELECT 1\n```\n## Possible prompt injection in artnot notes\n\n## Scope\n"
    hs = cal.hallazgos(md)
    assert [h["categoria"] for h in hs] == ["huerfanos", "instrucciones_inyectadas"] and hs[0]["sql"] == ["SELECT 1"]
    varias = cal.hallazgos("## R-05 · Contactos de proveedor huérfanos y duplicado (Media)\n```sql\nSELECT 1\n```\n")
    assert varias[0]["categorias"] == {"huerfanos", "duplicados"}


def test_yaml_en_espanol():
    y = {"objetos": [{"nombre": "movinv", "columnas": [
        {"nombre": "mov_id", "significado": "Identificador", "clave_primaria": "declarada", "clave_foranea": "no"},
        {"nombre": "mov_art", "significado": "Artículo", "clave_primaria": "no", "clave_foranea": "artmst.art_cd",
         "dato_personal": "no"},
        {"nombre": "mov_usr", "significado": "Usuario", "dato_personal": "si"}]}]}
    c = cal.columnas_del_yaml(y)
    assert set(c) == {"movinv.mov_id", "movinv.mov_art", "movinv.mov_usr"}
    assert cal._bool(cal._campo(c["movinv.mov_id"], "pk")) and not cal._bool(cal._campo(c["movinv.mov_art"], "pk"))
    assert cal._fk(cal._campo(c["movinv.mov_id"], "fk"), {}) is None
    assert cal._fk(cal._campo(c["movinv.mov_art"], "fk"), {}) == "artmst.art_cd"
    assert cal._bool(cal._campo(c["movinv.mov_usr"], "pii")) and not cal._bool(cal._campo(c["movinv.mov_art"], "pii"))


@pytest.mark.skipif(not DSN, reason="sin base")
@pytest.mark.parametrize("corrida", ["corrida_manual", "corrida_subagentes"])
def test_calidad_de_las_corridas_de_referencia(corrida):
    """Las corridas de las actividades 3 y 4 son la línea base del evaluador: si cambia, revisa el cambio."""
    r = cal.evaluar(corrida, DSN)
    d, k = r["diccionario"], r["riesgos"]
    assert d["columnas_cubiertas"] == 46 and d["significado_exacto"] >= 0.95
    for campo in ("llave_primaria", "llave_foranea", "datos_personales"):
        assert d[campo]["precision"] == 1.0 and d[campo]["recall"] == 1.0, campo
    assert k["encontrados"] == 12 and k["sql_reejecutado_ok"] == k["sql"]
    assert not next(x for x in k["detalle"] if x["id"] == "R-ALTERNO")["encontrado"]
