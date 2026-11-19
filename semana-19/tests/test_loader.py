"""Week 19, activity 4: tests of the one-shot loader. Offline by default ($0, no AWS).

- Offline (always run): the seed dump has the generator's row counts, the SQL copies match their sources, the insert
  builder casts every column, the role setup runs before the legacy SQL and its grants after it.
- Live (only with S19_DSN_LOCAL, a throwaway PostgreSQL that is never the lab database): the loader is idempotent,
  copilot_ro reads legado and cannot write, and order_writer exists with its grants.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
CARGADOR = S19 / "infra" / "loader"
sys.path.insert(0, str(CARGADOR / "vendor"))


def _cargar_handler():
    spec = importlib.util.spec_from_file_location("handler_loader", CARGADOR / "handler.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


H = _cargar_handler()

# Row counts the generator (inventory-copilot, seed 42) produces; the dump must match them.
FILAS_SEED_42 = {"suppliers": 12, "warehouses": 3, "products": 200, "stock": 600, "sales_daily": 36000}


def test_seed_42_tiene_las_filas_del_generador():
    seed = H._leer_seed()
    assert {k: len(v) for k, v in seed.items()} == FILAS_SEED_42


def test_seed_42_respeta_el_orden_y_las_columnas_de_carga():
    seed = H._leer_seed()
    for tabla, columnas, tipos in H.TABLAS:
        assert len(columnas) == len(tipos)
        assert all(len(fila) == len(columnas) for fila in seed[tabla]), tabla


def test_insert_convierte_cada_columna_en_la_base():
    tabla, columnas, tipos = next(t for t in H.TABLAS if t[0] == "products")
    sql = H.build_insert_sql(tabla, columnas, tipos)
    assert sql.startswith(f"INSERT INTO {tabla} (sku, name")
    for i, tipo in enumerate(tipos):
        assert f"a{i}::{tipo}" in sql
    assert ":a0::text[]" in sql and "unnest(" in sql


@pytest.mark.parametrize("copia,fuente", [
    ("legado.sql", "semana-10/legado/legado.sql"),
    ("artnot.sql", "semana-13/seguridad/artnot.sql"),
])
def test_copias_sql_coinciden_con_sus_fuentes(copia, fuente):
    assert (CARGADOR / copia).read_bytes() == (S19.parent / fuente).read_bytes(), copia


def test_ddl_copilot_es_el_esquema_de_la_semana_7_con_pgvector_al_inicio():
    copia = (CARGADOR / "ddl_copilot.sql").read_text(encoding="utf-8")
    fuente = (S19.parent / "semana-07" / "schema_completo.sql").read_text(encoding="utf-8")
    assert copia.endswith(fuente)


def test_ddl_copilot_empieza_por_la_extension_pgvector():
    primera = (CARGADOR / "ddl_copilot.sql").read_text(encoding="utf-8").splitlines()[0]
    assert primera == "CREATE EXTENSION IF NOT EXISTS vector;"


def test_roles_no_llevan_contrasena_y_copilot_ro_es_solo_lectura():
    assert "PASSWORD" not in H.ROLES_CREAR.upper()
    assert "default_transaction_read_only = on" in H.ROLES_CREAR
    assert "search_path = legado" in H.ROLES_CREAR


def test_roles_se_crean_antes_del_sql_legado_y_sus_permisos_despues(monkeypatch):
    llamadas = []

    class Fake:
        def run(self, sql, **kw):
            llamadas.append(sql)
            if sql.startswith("SELECT to_regclass"):
                return [[False]]
            return []

        def close(self):
            pass

    monkeypatch.setattr(H, "_secreto", lambda arn: {"username": "u", "password": "p"})
    monkeypatch.setattr(H, "_conectar", lambda host, usuario, clave: Fake())
    monkeypatch.setattr(H, "_cargar_seed", lambda con: {})
    H.handler({"secret_arn": "x", "db_host": "h"}, None)

    posicion = {"crear": None, "legado": None, "artnot": None, "permisos": None}
    for i, sql in enumerate(llamadas):
        if sql == H.ROLES_CREAR:
            posicion["crear"] = i
        elif sql == H.ROLES_PERMISOS:
            posicion["permisos"] = i
        elif "DROP SCHEMA IF EXISTS legado" in sql:
            posicion["legado"] = i
        elif "legado.artnot" in sql and "DROP TABLE" in sql:
            posicion["artnot"] = i
    assert posicion["crear"] is not None and posicion["legado"] is not None
    assert posicion["crear"] < posicion["legado"] < posicion["artnot"] < posicion["permisos"]


LIVE = os.environ.get("S19_DSN_LOCAL")


@pytest.mark.vivo  # deselected in CI (-m "not vivo"); run locally with -m vivo and S19_DSN_LOCAL
@pytest.mark.skipif(not LIVE, reason="prueba viva: define S19_DSN_LOCAL con una base de pruebas local")
def test_vivo_cargador_idempotente_y_copilot_ro_no_escribe():
    import pg8000.native as pg

    usuario, host, puerto = "postgres", "127.0.0.1", 55432

    def conectar(u):
        return pg.Connection(u, host=host, port=puerto, database="postgres")

    H._secreto = lambda arn: {"username": usuario, "password": ""}
    H._conectar = lambda h, u, c: conectar(usuario)
    primera = H.handler({"secret_arn": "local", "db_host": "local"}, None)
    segunda = H.handler({"secret_arn": "local", "db_host": "local"}, None)
    assert primera["filas"] == segunda["filas"] == FILAS_SEED_42

    con = conectar(usuario)
    conteo = con.run("SELECT (SELECT count(*) FROM suppliers) + (SELECT count(*) FROM sales_daily)")[0][0]
    assert conteo == 12 + 36000

    ro = conectar("copilot_ro")
    assert ro.run("SELECT count(*) FROM legado.prvmst")[0][0] == 12
    with pytest.raises(Exception):
        ro.run("INSERT INTO legado.artnot (not_id, not_art, not_txt, not_fch) VALUES (999,'X','x','2026-01-01')")
    assert con.run("SELECT count(*) FROM pg_roles WHERE rolname = 'order_writer'")[0][0] == 1


def test_scramp_vendorizado_tiene_make_channel_binding():
    # pg8000 1.31.2 calls scramp.make_channel_binding on the TLS path (RDS). scramp 1.5.0 removed it: that broke
    # the first real invocation of the loader. Pinned to 1.4.8 in infra/loader/vendor.
    import scramp
    assert hasattr(scramp, "make_channel_binding")
    assert scramp.__file__.startswith(str(CARGADOR / "vendor"))


def test_pruebas_permisos_marca_denegado_y_siempre_hace_rollback_y_revoca():
    llamadas = []

    class Error(Exception):
        args = ({"C": "42501", "M": "permission denied"},)

    class Fake:
        def run(self, sql, **kw):
            llamadas.append(sql)
            if sql.startswith("INSERT"):
                raise Error()
            if sql.startswith("SELECT count"):
                return [[12]]
            return []

    resultado = H._pruebas_permisos(Fake())
    assert resultado["insert_legado_artnot"] == "DENEGADO"
    assert resultado["sqlstate"] == "42501"
    assert resultado["select_legado_prvmst"] == 12
    assert llamadas[0] == "GRANT copilot_ro TO CURRENT_USER"
    assert "ROLLBACK" in llamadas
    assert llamadas[-1] == "REVOKE copilot_ro FROM CURRENT_USER"


def test_pruebas_permisos_marca_permitido_si_el_insert_funciona():
    class Fake:
        def run(self, sql, **kw):
            return [[12]] if sql.startswith("SELECT count") else []

    assert H._pruebas_permisos(Fake())["insert_legado_artnot"] == "PERMITIDO"


# ---------------------------------------------------------------- activity 8: the approval test reads its orders

class _FakeLectura:
    def __init__(self):
        self.sql = []

    def run(self, sql, **kw):
        self.sql.append((sql, kw))
        if sql.startswith("SELECT po_id"):
            return [[7, "SKU-0002", "APPROVED", "sub-c", "sub-a", "gerente", "gerente"]]
        if sql.startswith("SELECT status"):
            return [["APPROVED", 1], ["PENDING_APPROVAL", 1]]
        if sql.startswith("SELECT has_table_privilege"):
            return [[kw["r"] == "order_writer" and kw["p"] != "DELETE"]]
        return []


def test_leer_ordenes_solo_lee_en_una_transaccion_de_solo_lectura_que_se_revierte():
    con = _FakeLectura()
    r = H._leer_ordenes(con, [7])
    sentencias = [s for s, _ in con.sql]
    assert sentencias[:2] == ["BEGIN", "SET TRANSACTION READ ONLY"] and sentencias[-1] == "ROLLBACK"
    assert all(s.split()[0] in ("BEGIN", "SET", "SELECT", "ROLLBACK") for s in sentencias)
    assert r["ordenes"] == [{"po_id": 7, "sku": "SKU-0002", "status": "APPROVED", "requested_by": "sub-c",
                             "decided_by": "sub-a", "decided_level": "gerente", "required_level": "gerente"}]
    assert r["por_estado"] == {"APPROVED": 1, "PENDING_APPROVAL": 1}
    assert r["privilegios"]["order_writer"] == {"SELECT": True, "INSERT": True, "UPDATE": True, "DELETE": False}
    assert not any(r["privilegios"]["copilot_ro"].values())
    assert ("SELECT po_id, sku, status, requested_by, decided_by, decided_level, required_level FROM "
            "public.purchase_orders WHERE po_id = ANY(CAST(:ids AS int[])) ORDER BY po_id", {"ids": [7]}) in con.sql


@pytest.mark.parametrize("ids", [None, [], [0], ["7"], [True], list(range(1, 22))])
def test_leer_ordenes_rechaza_ids_invalidos_antes_de_tocar_la_base(ids):
    con = _FakeLectura()
    with pytest.raises(ValueError):
        H._leer_ordenes(con, ids)
    assert con.sql == []


def test_leer_ordenes_revierte_aunque_falle_la_consulta():
    class Falla(_FakeLectura):
        def run(self, sql, **kw):
            super().run(sql, **kw)
            if sql.startswith("SELECT po_id"):
                raise RuntimeError("x")
            return []

    con = Falla()
    with pytest.raises(RuntimeError):
        H._leer_ordenes(con, [1])
    assert con.sql[-1][0] == "ROLLBACK"


class _FakeEsperados:
    def __init__(self):
        self.sql = []

    def run(self, sql, **kw):
        self.sql.append(sql)
        if sql.startswith(("SELECT", "WITH")):
            from decimal import Decimal
            import datetime as dt
            return [["SKU-0001", Decimal("12.50"), dt.date(2026, 11, 5), 3]]
        return []


def test_esperados_corre_cada_consulta_en_solo_lectura_con_timeout_y_revierte():
    con = _FakeEsperados()
    r = H._esperados(con, {"s03-es/proveedor": "SELECT 1;", "c02-es/x": "WITH a AS (SELECT 1) SELECT * FROM a"})
    assert r["esperados"]["s03-es/proveedor"] == [["SKU-0001", 12.5, "2026-11-05", 3]]
    bloques = [con.sql[i:i + 6] for i in range(0, len(con.sql), 6)]
    for b in bloques:
        assert b[:4] == ["BEGIN", "SET TRANSACTION READ ONLY", "SET LOCAL statement_timeout = 15000",
                         "SET LOCAL search_path = public"] and b[5] == "ROLLBACK"
    assert con.sql[4] == "SELECT 1"


@pytest.mark.parametrize("consultas", [None, {}, {"k": "DELETE FROM products"}, {"k": "SELECT 1; DROP TABLE x"},
                                       {"k": "  "}, {f"k{i}": "SELECT 1" for i in range(41)}])
def test_esperados_rechaza_lo_que_no_es_una_sola_consulta_antes_de_tocar_la_base(consultas):
    con = _FakeEsperados()
    with pytest.raises(ValueError):
        H._esperados(con, consultas)
    assert con.sql == []


def test_esperados_revierte_aunque_la_consulta_falle():
    class Falla(_FakeEsperados):
        def run(self, sql, **kw):
            self.sql.append(sql)
            if sql.startswith("SELECT"):
                raise RuntimeError("timeout")
            return []

    con = Falla()
    with pytest.raises(RuntimeError):
        H._esperados(con, {"k": "SELECT 1"})
    assert con.sql[-1] == "ROLLBACK"
