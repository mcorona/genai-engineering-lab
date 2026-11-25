import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

S15 = Path(__file__).resolve().parents[1]
S14 = S15.parent / "semana-14"
S13 = S15.parent / "semana-13"
for p in (S13, S14, S15):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

HAY_BASE = bool(os.environ.get("PG_ADMIN_DSN"))
VENVS = Path(os.environ.get("VENVS_S15", S15 / ".venvs"))


def tarea(id_: str, adm=None) -> dict:
    lang = id_.rsplit("-", 1)[1]
    t = next(json.loads(x) for x in open(S13 / "golden" / f"tareas_{lang}.jsonl", encoding="utf-8")
             if json.loads(x)["id"] == id_)
    if adm is not None:   # the expected result is recomputed on the database where the test runs (as in the week 13 CI)
        for s in t["salida"].values():
            s["esperado"] = [list(f) for f in adm.execute(s["sql_ref"]).fetchall()]
    return t


@pytest.fixture(scope="session")
def adm():
    if not HAY_BASE:
        pytest.skip("no database (PG_ADMIN_DSN)")
    import psycopg
    c = psycopg.connect(os.environ["PG_ADMIN_DSN"], autocommit=True)
    c.execute("SET search_path = copilot, public")
    yield c
    c.close()


@pytest.fixture(scope="session")
def entorno(adm):
    """The week 14 MCP server (HTTP + OAuth) with a lab issuer: the same JWT validation as with Keycloak."""
    spec = importlib.util.spec_from_file_location("seguridad14_arnes", S14 / "seguridad" / "correr.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    e = m.Entorno("prueba", con_base=True)
    yield e
    e.cerrar()


@pytest.fixture(scope="session")
def conexion_verificador(adm):
    from herramientas.conexion import conectar
    c = conectar()[0]
    yield c
    c.close()
