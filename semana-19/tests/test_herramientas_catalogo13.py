"""Week 19, activity 8: buscar_regla_negocio and muestrear_valores, back from week 13, offline ($0, no database).

The first live eval found them missing (10/20 against week 17's 20/20) while the system prompt asked for them.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente import capa_determinista as C  # noqa: E402
from herramientas import catalogo13 as K  # noqa: E402
from herramientas import contrato  # noqa: E402
from herramientas import handler as H  # noqa: E402

REGLAS = json.loads((S19.parent / "semana-13" / "golden" / "reglas_negocio.json").read_text(encoding="utf-8"))["reglas"]


class Conexion:
    """Answers the sampling query and the distinct count; records every statement."""
    def __init__(self):
        self.sql = []

    def run(self, sql, **kw):
        self.sql.append(sql)
        if sql.startswith("SELECT * FROM") and "COUNT(DISTINCT" in sql:
            return [[2]]
        if sql.startswith("SELECT * FROM"):
            return [["MX", 9], ["US", 3]]
        return []

    def close(self):
        pass


def llamar(nombre, args, conectar=None):
    return H.handler(contrato.entrada_de_herramienta(nombre, args), None, conectar=conectar)


def test_el_catalogo_del_agente_y_el_de_la_lambda_son_el_mismo_y_traen_las_herramientas_del_prompt():
    assert C.HERRAMIENTAS == contrato.HERRAMIENTAS
    nombres = [d["name"] for d in C.definiciones_semana19()]
    assert nombres == list(contrato.HERRAMIENTAS)
    from ia import prompts_sistema
    texto = json.dumps(vars(prompts_sistema), default=str)
    for n in ("describir_esquema", "buscar_regla_negocio", "muestrear_valores", "ejecutar_sql"):
        assert n in texto and n in nombres


def test_la_regla_de_riesgo_llega_en_los_dos_idiomas_y_es_la_de_la_semana_13():
    res = llamar("buscar_regla_negocio", {"consulta": "SKU críticos en riesgo"})
    assert "error" not in res
    riesgo = {r["id"]: r for r in REGLAS}["R-RIESGO"]
    (r,) = [x for x in res["reglas"] if x["id"] == "R-RIESGO"]
    assert r["definicion"] == riesgo["es"] and r["definition"] == riesgo["en"] and r["fuente"] == riesgo["fuente"]
    assert llamar("buscar_regla_negocio", {"consulta": "R-COB"})["reglas"][0]["id"] == "R-COB"


def test_sin_coincidencias_sugiere_los_ids_y_argumentos_extra_se_rechazan():
    res = llamar("buscar_regla_negocio", {"consulta": "zzzz qqqq"})
    assert res["reglas"] == [] and "R-RIESGO" in res["sugerencia"]
    res = llamar("buscar_regla_negocio", {"consulta": "riesgo", "rol": "director"})
    assert res["error"] == "argumentos_invalidos"


def test_muestrear_valores_pasa_por_la_guardia_y_la_transaccion_de_solo_lectura():
    con = Conexion()
    res = llamar("muestrear_valores", {"tabla": "prvmst", "columna": "prv_pais"}, conectar=lambda: con)
    assert res == {"tabla": "prvmst", "columna": "prv_pais", "valores_distintos": 2,
                   "valores": [{"valor": "MX", "filas": 9}, {"valor": "US", "filas": 3}]}
    consultas = [s for s in con.sql if s.startswith("SELECT * FROM")]
    assert len(consultas) == 2 and all("legado.prvmst" in s for s in consultas)
    assert con.sql.count("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY") == 2


def test_una_columna_o_tabla_desconocida_no_llega_a_la_base():
    def no_debe():
        raise AssertionError("conectó")
    res = llamar("muestrear_valores", {"tabla": "prvmst", "columna": "prv_pais; DROP TABLE x"}, conectar=no_debe)
    assert res["error"] == "columna_desconocida"
    res = llamar("muestrear_valores", {"tabla": "pg_shadow", "columna": "passwd"}, conectar=no_debe)
    assert res["error"] == "argumentos_invalidos"


def test_el_modulo_de_la_semana_13_se_carga_de_su_archivo_sin_pisar_el_paquete_herramientas():
    K.semana13()
    rutas = set(sys.modules["herramientas"].__path__)
    assert rutas == {str(S19 / "herramientas")} and str(S19.parent / "semana-13" / "herramientas") not in rutas
    assert sys.modules[K.NOMBRE].__file__ == str(K.ARCHIVO_S13)
