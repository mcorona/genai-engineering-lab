"""Tests of the MCP server (activity 4): the same catalog, schemas, permissions and responses as the
native tools. They start the server over stdio with the MCP client."""
import json

import pytest
from conftest import HAY_BASE, herramientas
from herramientas import Contexto, Herramientas, definiciones
from servidor_mcp.cliente import HerramientasMCP


@pytest.fixture(scope="module")
def mcp_analista():
    with HerramientasMCP("analista") as m:
        yield m


@pytest.fixture(scope="module")
def mcp_almacenista():
    with HerramientasMCP("almacenista") as m:
        yield m


def test_mismo_catalogo(mcp_analista):
    assert mcp_analista.definiciones() == definiciones()


CASOS = [
    ("describir_esquema", {}),
    ("describir_esquema", {"tablas": ["vtadia"]}),
    ("buscar_regla_negocio", {"consulta": "días de cobertura"}),
    ("buscar_regla_negocio", {"consulta": "zzz"}),
    ("validar_sql", {"sql": "DELETE FROM exidet"}),
    ("validar_sql", {"sql": "SELECT lo_create(0)"}),
    ("validar_sql", {"sql": "SELECT content FROM semana10.chunks"}),
    ("ejecutar_sql", {"sql": "SELECT 1", "roles": ["finanzas"]}),
    ("ejecutar_sql", {"sql": "SELECT 1; SELECT 2"}),
    ("muestrear_valores", {"tabla": "artmst", "columna": "art_cst", "limite": 99}),
    ("no_existe", {}),
]


def normal(r):
    return json.loads(json.dumps(r, ensure_ascii=False, default=str))


@pytest.mark.parametrize("nombre,args", CASOS)
def test_misma_respuesta_sin_base(nombre, args, mcp_analista, mcp_almacenista):
    if HAY_BASE and nombre in ("validar_sql",) and "DELETE" not in args.get("sql", "") and "lo_create" not in args.get("sql", ""):
        pytest.skip("con base, validar_sql agrega EXPLAIN; se compara en la prueba con base")
    for usuario, m in (("analista", mcp_analista), ("almacenista", mcp_almacenista)):
        nativo = Herramientas(Contexto.de_usuario(usuario)).llamar(nombre, args)
        if HAY_BASE and nativo.get("error", {}).get("tipo") == "sin_base":
            continue  # the server does have a database; those cases are covered below
        assert normal(m.llamar(nombre, args)) == normal(nativo), (usuario, nombre, args)


def test_permisos_del_host_no_del_modelo(mcp_almacenista):
    r = mcp_almacenista.llamar("describir_esquema", {})
    assert [t["tabla"] for t in r["tablas"]] == ["artmst", "almmst", "exidet", "artnot"]
    assert mcp_almacenista.llamar("validar_sql", {"sql": "SELECT vta_art FROM vtadia"})["error"]["tipo"] == "permiso_denegado"
    assert mcp_almacenista.llamar("describir_esquema", {"usuario": "analista"})["error"]["tipo"] == "argumentos_invalidos"


def test_is_error_del_protocolo(mcp_analista):
    mcp_analista.llamar("validar_sql", {"sql": "DROP TABLE artmst"})
    assert mcp_analista.ctx.llamadas[-1]["is_error"] is True
    mcp_analista.llamar("buscar_regla_negocio", {"consulta": "R-COB"})
    assert mcp_analista.ctx.llamadas[-1]["is_error"] is False


@pytest.mark.parametrize("sql", [
    "SELECT prv_pais, COUNT(*) FROM prvmst GROUP BY 1 ORDER BY 1",
    "SELECT art_cd FROM artmst ORDER BY art_cd",
    "SELECT art_precio FROM artmst",
    "SELECT art_cd, SUM(art_cst) FROM artmst",
])
def test_misma_ejecucion_con_base(sql, conexion, mcp_analista):
    nativo = herramientas("analista", conexion).llamar("ejecutar_sql", {"sql": sql, "max_filas": 200})
    assert normal(mcp_analista.llamar("ejecutar_sql", {"sql": sql, "max_filas": 200})) == normal(nativo)
