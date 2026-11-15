"""Tests of the week 13 tools (activity 2).

Without a database: the contract (strict JSON Schema, invalid arguments, extra fields such as roles), business rules and the
SQL guard. With a database (PG_ADMIN_DSN, NLQ_LEGADO_DSN or PG_DSN): schema by permissions, sampling, EXPLAIN, execution,
truncation, timeouts, database errors and defense in depth (read-only even if the guard is bypassed).
"""
import json

import pytest
from conftest import herramientas
from herramientas import Contexto, Herramientas, definiciones
from herramientas.herramientas import ErrorHerramienta

GUARD = Herramientas(Contexto.de_usuario("analista"))


def err(res):
    assert res["ok"] is False, res
    assert set(res["error"]) == {"tipo", "mensaje", "sugerencia"}
    return res["error"]["tipo"]


def guard(sql, usuario="analista"):
    try:
        Herramientas(Contexto.de_usuario(usuario))._guard(sql)
        return "ok"
    except ErrorHerramienta as e:
        return e.tipo


# ---------- contract ----------

def test_definiciones_estrictas():
    defs = definiciones()
    assert [d["name"] for d in defs] == ["describir_esquema", "buscar_regla_negocio", "muestrear_valores", "validar_sql",
                                         "ejecutar_sql", "proponer_orden_compra"]
    for d in defs:
        s = d["input_schema"]
        assert s["type"] == "object" and s["additionalProperties"] is False
        assert d["description"]
        assert not {"roles", "usuario", "rol", "tenant"} & set(s["properties"]), "el modelo no debe poder elegir permisos"
        json.dumps(d)


def test_requeridos():
    req = {d["name"]: set(d["input_schema"].get("required", [])) for d in definiciones()}
    assert req["describir_esquema"] == set()
    assert req["buscar_regla_negocio"] == {"consulta"}
    assert req["muestrear_valores"] == {"tabla", "columna"}
    assert req["validar_sql"] == {"sql"} and req["ejecutar_sql"] == {"sql"}
    assert req["proponer_orden_compra"] == {"sku", "cantidad", "motivo"}


@pytest.mark.parametrize("nombre,args", [
    ("ejecutar_sql", {"sql": "SELECT 1", "roles": ["finanzas"]}),       # the model tries to escalate
    ("ejecutar_sql", {"sql": "SELECT 1", "max_filas": 100000}),          # out of range
    ("ejecutar_sql", {}),                                                # sql is missing
    ("describir_esquema", {"tablas": ["pg_roles"]}),                     # table outside the enum
    ("buscar_regla_negocio", {"consulta": ""}),
    ("muestrear_valores", {"tabla": "artmst", "columna": "art_cst", "limite": 999}),
])
def test_argumentos_invalidos(h_sin_base, nombre, args):
    assert err(h_sin_base.llamar(nombre, args)) == "argumentos_invalidos"


def test_herramienta_desconocida(h_sin_base):
    assert err(h_sin_base.llamar("borrar_tabla", {})) == "herramienta_desconocida"


def test_bitacora(h_sin_base):
    h_sin_base.llamar("buscar_regla_negocio", {"consulta": "cobertura"})
    h_sin_base.llamar("ejecutar_sql", {"x": 1})
    assert [(c["herramienta"], c["ok"], c["error"]) for c in h_sin_base.ctx.llamadas] == [
        ("buscar_regla_negocio", True, None), ("ejecutar_sql", False, "argumentos_invalidos")]


# ---------- describir_esquema without a database (it does not need one) ----------

def test_esquema_analista(h_sin_base):
    r = h_sin_base.llamar("describir_esquema", {})
    assert r["ok"] and [t["tabla"] for t in r["tablas"]] == ["prvmst", "artmst", "almmst", "exidet", "vtadia", "ocpcab", "artnot"]
    assert "original" not in json.dumps(r), "no se revelan los nombres originales"


def test_esquema_por_permisos():
    h = Herramientas(Contexto.de_usuario("almacenista"))
    r = h.llamar("describir_esquema", {})
    assert [t["tabla"] for t in r["tablas"]] == ["artmst", "almmst", "exidet", "artnot"]
    art = next(t for t in r["tablas"] if t["tabla"] == "artmst")
    assert "art_cst" not in [c["columna"] for c in art["columnas"]], "columna restringida oculta"
    assert err(h.llamar("describir_esquema", {"tablas": ["vtadia"]})) == "tabla_no_disponible"


# ---------- business rules ----------

@pytest.mark.parametrize("consulta,idioma,esperada", [
    ("días de cobertura", "es", "R-COB"),
    ("days of coverage", "en", "R-COB"),
    ("SKU crítico en riesgo", "es", "R-RIESGO"),
    ("excedente CEDIS transferir", "es", "R-EXCEDENTE"),
    ("purchase order proposals", "en", "R-PROPUESTA"),
    ("quién aprueba una orden", "es", "R-OC-APRUEBA"),
    ("clase A inventario cíclico", "es", "R-ABC"),
    ("r-cob", "es", "R-COB"),
])
def test_regla(consulta, idioma, esperada):
    h = Herramientas(Contexto("x", ["compras"], idioma=idioma))
    r = h.llamar("buscar_regla_negocio", {"consulta": consulta})
    assert r["ok"] and r["reglas"][0]["id"] == esperada, [x["id"] for x in r["reglas"]]
    assert r["reglas"][0]["definicion"] and r["reglas"][0]["fuente"]


def test_regla_idioma():
    es = Herramientas(Contexto("x", [], idioma="es")).llamar("buscar_regla_negocio", {"consulta": "R-COB"})
    en = Herramientas(Contexto("x", [], idioma="en")).llamar("buscar_regla_negocio", {"consulta": "R-COB"})
    assert es["reglas"][0]["definicion"].startswith("Días") and en["reglas"][0]["definicion"].startswith("Days")


def test_regla_sin_coincidencia(h_sin_base):
    r = h_sin_base.llamar("buscar_regla_negocio", {"consulta": "zzz qqq"})
    assert r["ok"] and r["reglas"] == [] and "R-COB" in r["sugerencia"]


# ---------- guard (no database) ----------

@pytest.mark.parametrize("sql,tipo", [
    ("SELECT art_cd FROM artmst WHERE art_crt", "ok"),
    ("WITH t AS (SELECT exi_art, SUM(exi_qty) q FROM exidet GROUP BY 1) SELECT * FROM t WHERE q > 10", "ok"),
    ("SELECT a.art_cd FROM legado.artmst a JOIN legado.prvmst p ON p.prv_id = a.art_prv", "ok"),
    ("SELECT 1 UNION SELECT 2", "ok"),
    ("DELETE FROM exidet WHERE exi_alm = 1", "escritura_bloqueada"),
    ("UPDATE artmst SET art_cst = 0", "escritura_bloqueada"),
    ("INSERT INTO ocpcab VALUES (1)", "escritura_bloqueada"),
    ("DROP TABLE artmst", "escritura_bloqueada"),
    ("CREATE TABLE x AS SELECT * FROM artmst", "escritura_bloqueada"),
    ("SELECT * INTO copia FROM artmst", "escritura_bloqueada"),
    ("SELECT art_cd FROM artmst FOR UPDATE", "escritura_bloqueada"),
    ("SET default_transaction_read_only = off", "escritura_bloqueada"),
    ("SELECT 1; DELETE FROM exidet", "multiples_sentencias"),
    ("SELECT lo_create(0)", "funcion_prohibida"),
    ("SELECT set_config('default_transaction_read_only', 'off', false)", "funcion_prohibida"),
    ("SELECT pg_sleep(10)", "funcion_prohibida"),
    ("SELECT pg_read_file('/etc/passwd')", "funcion_prohibida"),
    ("SELECT nextval('s')", "funcion_prohibida"),
    ("SELECT content FROM semana10.chunks", "permiso_denegado"),
    ("SELECT rolname FROM pg_catalog.pg_roles", "permiso_denegado"),
    ("SELECT * FROM products", "tabla_no_disponible"),
    ("SELEC art_cd FRM artmst", "sql_invalido"),
    ("SELECT art_cd FROM artmst WHERE art_dsc = 'sin cerrar", "sql_invalido"),     # TokenError, no ParseError
    ('SELECT art_cd AS "sin cerrar FROM artmst', "sql_invalido"),
])
def test_guard(sql, tipo):
    assert guard(sql) == tipo


@pytest.mark.parametrize("usuario,sql,tipo", [
    ("almacenista", "SELECT vta_art FROM vtadia", "permiso_denegado"),            # another role's table
    ("almacenista", "SELECT art_cd, art_cst FROM artmst", "permiso_denegado"),    # restricted column
    ("vendedor", "SELECT * FROM artmst", "permiso_denegado"),                     # * would include art_cst
    ("vendedor", "SELECT COUNT(*) FROM artmst", "ok"),                            # COUNT(*) exposes no columns
    ("vendedor", "SELECT art_cd, art_dsc FROM artmst", "ok"),
    ("analista", "SELECT SUM(art_cst) FROM artmst", "ok"),
])
def test_guard_permisos(usuario, sql, tipo):
    assert guard(sql, usuario) == tipo


def test_permiso_denegado_estructurado():
    h = Herramientas(Contexto.de_usuario("almacenista"))
    e = h.llamar("validar_sql", {"sql": "SELECT vta_art FROM vtadia"})["error"]
    assert e["tipo"] == "permiso_denegado" and "vtadia" in e["mensaje"] and "exidet" in e["sugerencia"]


def test_sin_base_no_ejecuta(h_sin_base):
    assert err(h_sin_base.llamar("ejecutar_sql", {"sql": "SELECT 1"})) == "sin_base"


# ---------- with a database ----------

def test_rol_de_solo_lectura(conexion):
    rol = conexion.execute("SELECT current_user").fetchone()[0]
    puede = conexion.execute("SELECT bool_or(has_table_privilege(current_user, c.oid, 'INSERT,UPDATE,DELETE')) "
                             "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'legado'").fetchone()[0]
    assert rol in ("copilot_nlq", "copilot_ro") and not puede


def test_ejecutar(conexion):
    h = herramientas("analista", conexion)
    r = h.llamar("ejecutar_sql", {"sql": "SELECT prv_pais, COUNT(*) FROM prvmst GROUP BY 1 ORDER BY 1"})
    assert r["ok"] and r["columnas"] == ["prv_pais", "count"] and r["total_filas"] >= 3 and not r["truncado"]


def test_truncado(conexion):
    r = herramientas("analista", conexion).llamar("ejecutar_sql", {"sql": "SELECT art_cd FROM artmst", "max_filas": 5})
    assert r["ok"] and r["total_filas"] == 200 and r["filas_devueltas"] == 5 and r["truncado"]


def test_cero_filas_con_pista(conexion):
    r = herramientas("analista", conexion).llamar("ejecutar_sql", {"sql": "SELECT prv_nm FROM prvmst WHERE prv_pais = 'Alemania'"})
    assert r["ok"] and r["total_filas"] == 0 and "muestrear_valores" in r["nota"]


def test_muestrear(conexion):
    h = herramientas("analista", conexion)
    r = h.llamar("muestrear_valores", {"tabla": "prvmst", "columna": "prv_pais"})
    assert r["ok"] and "DE" in [v["valor"] for v in r["valores"]]
    assert err(h.llamar("muestrear_valores", {"tabla": "prvmst", "columna": "inventada"})) == "columna_desconocida"
    alm = herramientas("almacenista", conexion)
    assert err(alm.llamar("muestrear_valores", {"tabla": "artmst", "columna": "art_cst"})) == "permiso_denegado"
    assert err(alm.llamar("muestrear_valores", {"tabla": "vtadia", "columna": "vta_art"})) == "permiso_denegado"


def test_validar_con_explain(conexion):
    h = herramientas("analista", conexion)
    assert h.llamar("validar_sql", {"sql": "SELECT art_cd FROM artmst"})["ok"]
    r = h.llamar("validar_sql", {"sql": "SELECT art_precio FROM artmst"})
    assert err(r) == "error_sql" and "42703" in r["error"]["mensaje"] and "describir_esquema" in r["error"]["sugerencia"]


def test_errores_de_base(conexion):
    h = herramientas("analista", conexion)
    r = h.llamar("ejecutar_sql", {"sql": "SELECT art_cd, SUM(art_cst) FROM artmst"})
    assert err(r) == "error_sql" and "42803" in r["error"]["mensaje"]
    r = h.llamar("ejecutar_sql", {"sql": "SELECT art_cst / 0 FROM artmst"})
    assert err(r) == "error_sql" and "NULLIF" in r["error"]["sugerencia"]


def test_tiempo_agotado(conexion):
    h = herramientas("analista", conexion, timeout_ms=200)
    r = h.llamar("ejecutar_sql", {"sql": "SELECT COUNT(*) FROM vtadia a, vtadia b"})
    assert err(r) == "tiempo_agotado"


def test_defensa_en_profundidad(conexion):
    """Even if the guard let something through, the session is read-only and the role has no write privileges."""
    h = herramientas("analista", conexion)
    for sql in ("SELECT lo_create(0)", "DELETE FROM exidet WHERE false", "CREATE TEMP TABLE t AS SELECT 1"):
        with pytest.raises(ErrorHerramienta) as e:
            h._correr(sql)
        assert e.value.tipo in ("escritura_bloqueada", "permiso_denegado", "error_sql")
    assert conexion.execute("SELECT count(*) FROM pg_largeobject_metadata").fetchone()[0] >= 0


def test_golden_simple_con_herramientas(conexion):
    """The tool reproduces a gold-set result (s03: the supplier with the most critical products)."""
    import pathlib
    tarea = next(json.loads(x) for x in open(pathlib.Path(__file__).parents[1] / "golden" / "tareas_es.jsonl")
                 if json.loads(x)["id"] == "s03-es")
    r = herramientas("analista", conexion).llamar("ejecutar_sql", {"sql":
        "SELECT p.prv_nm FROM artmst a JOIN prvmst p ON p.prv_id = a.art_prv WHERE a.art_crt "
        "GROUP BY p.prv_nm ORDER BY COUNT(*) DESC, p.prv_nm LIMIT 1"})
    # the expected result is recomputed on this database (in CI the data is synthetic, seed 42) with the reference SQL
    import os
    import psycopg
    with psycopg.connect(os.environ.get("PG_ADMIN_DSN") or os.environ["PG_DSN"]) as ref:
        ref.execute("SET search_path = copilot, public")
        esperado = [list(f) for f in ref.execute(tarea["salida"]["filas"]["sql_ref"]).fetchall()]
    assert r["filas"] == esperado


def test_nunca_excepcion_hacia_el_modelo(h_sin_base, monkeypatch):
    def rompe(*a, **k):
        raise RuntimeError("falla inesperada")
    monkeypatch.setattr(h_sin_base, "_guard", rompe)
    r = h_sin_base.llamar("validar_sql", {"sql": "SELECT 1"})
    assert r["ok"] is False and r["error"]["tipo"] == "error_interno" and "RuntimeError" in r["error"]["mensaje"]


# ---------- proposals (never executed) ----------

def test_propuesta_solo_se_registra(h_sin_base):
    r = h_sin_base.llamar("proponer_orden_compra", {"sku": "SKU-0009", "cantidad": 300, "motivo": "reorden"})
    assert r["ok"] and r["propuesta"]["estado"] == "PENDING_APPROVAL" and r["propuesta"]["ejecutada"] is False
    assert "no se escribió nada" in r["nota"] and h_sin_base.ctx.propuestas == [r["propuesta"]]


@pytest.mark.parametrize("args", [
    {"sku": "SKU-9", "cantidad": 1, "motivo": "x"}, {"sku": "SKU-0009", "cantidad": 0, "motivo": "x"},
    {"sku": "SKU-0009", "cantidad": 1, "motivo": "x", "estado": "APPROVED"},  # the model cannot approve
])
def test_propuesta_argumentos(h_sin_base, args):
    assert err(h_sin_base.llamar("proponer_orden_compra", args)) == "argumentos_invalidos"


def test_propuesta_por_rol():
    h = Herramientas(Contexto.de_usuario("almacenista"))
    assert err(h.llamar("proponer_orden_compra", {"sku": "SKU-0009", "cantidad": 5, "motivo": "x"})) == "permiso_denegado"


def test_reglas_extra_solo_en_su_contexto():
    extra = [{"id": "R-X", "nombre": "Regla de prueba", "nombre_en": "Test rule", "fuente": "prueba", "es": "zzzqqq", "en": "zzzqqq"}]
    con = Herramientas(Contexto("x", [], reglas_extra=extra)).llamar("buscar_regla_negocio", {"consulta": "zzzqqq"})
    sin = Herramientas(Contexto("x", [])).llamar("buscar_regla_negocio", {"consulta": "zzzqqq"})
    assert con["reglas"][0]["id"] == "R-X" and sin["reglas"] == []
