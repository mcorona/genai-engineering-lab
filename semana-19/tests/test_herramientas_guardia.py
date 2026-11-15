"""Week 19, activity 6: the tools Lambda's SQL guard, offline ($0, no database).

Every write or out-of-scope statement must be rejected by the guard before a connection exists. The connection is a
fake that fails the test if anything calls it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from herramientas.guardia_sql import ToolError, guard  # noqa: E402

OBJETOS = {"prvmst", "artnot", "stock", "products"}
ESQUEMA = "legado"


ESCRITURAS = [
    "INSERT INTO legado.artnot (not_id, not_art, not_txt, not_fch) VALUES (1,'X','x','2026-01-01')",
    "UPDATE legado.prvmst SET prv_nom = 'x'",
    "DELETE FROM legado.prvmst",
    "DROP TABLE legado.artnot",
    "TRUNCATE legado.prvmst",
    "ALTER TABLE legado.prvmst ADD COLUMN x int",
    "GRANT ALL ON legado.prvmst TO copilot_ro",
    "CREATE TABLE legado.nuevo (id int)",
    "WITH borrado AS (DELETE FROM legado.prvmst RETURNING *) SELECT * FROM borrado",
    "SELECT 1; DELETE FROM legado.prvmst",
    "SELECT set_config('search_path', 'public', false)",
    "SELECT pg_sleep(30)",
    "SELECT lo_create(0)",
]

FUERA_DE_ESQUEMA = [
    "SELECT * FROM public.suppliers",
    "SELECT * FROM pg_catalog.pg_roles",
    "SELECT * FROM legado_otro.prvmst",
]


@pytest.mark.parametrize("sql", ESCRITURAS)
def test_escrituras_se_rechazan(sql):
    with pytest.raises(ToolError):
        guard(sql, ESQUEMA, OBJETOS)


@pytest.mark.parametrize("sql", FUERA_DE_ESQUEMA)
def test_otro_esquema_se_rechaza(sql):
    with pytest.raises(ToolError):
        guard(sql, ESQUEMA, OBJETOS)


def test_objeto_desconocido_se_rechaza():
    with pytest.raises(ToolError):
        guard("SELECT * FROM legado.no_existe", ESQUEMA, OBJETOS)


def test_select_valido_pasa_y_se_normaliza():
    sql = guard("SELECT prv_nom FROM legado.prvmst WHERE prv_id = 1", ESQUEMA, {"prvmst"})
    assert "prvmst" in sql.lower()
