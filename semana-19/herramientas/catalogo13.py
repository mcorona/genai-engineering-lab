"""Week 19, activity 8: the two week 13 tools the AWS port had left out, reused from week 13's own file.

The eval against the deployed endpoint (eval/eval_aws.py, first run of 2026-11-19) scored 10/20 against week 17's
20/20: the system prompt (ia/prompts_sistema.py) asks for buscar_regla_negocio and muestrear_valores, but activity 6
had narrowed the catalog to describir_esquema, ejecutar_sql and proponer_orden_compra. Without the rule the agent made
up its own definition (r02: "at risk" as stock under the reorder point instead of coverage days under lead time).

- buscar_regla_negocio: week 13's search (semana-13/herramientas/herramientas.py, `_buscar_regla_negocio`) over week
  13's rules (semana-13/golden/reglas_negocio.json), no database. The tools Lambda does not know the task's language,
  so each rule carries its definition in both languages.
- muestrear_valores: week 13's contract (MuestrearValores, the data dictionary of semana-10/legado) and week 13's
  query, run through this Lambda's own path: the week 16 guard first, then copilot_ro in a read-only transaction.

Week 13's module is loaded from its file under its own name (its package is also called `herramientas`), as
agente/capa_determinista.py does with week 17's core. It needs pydantic and sqlglot, which the agent package carries.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Callable

RAIZ = Path(__file__).resolve().parents[2]          # the repository, or the package root in the Lambda
ARCHIVO_S13 = RAIZ / "semana-13" / "herramientas" / "herramientas.py"
NOMBRE = "herramientas_semana13"


def semana13():
    if NOMBRE not in sys.modules:
        spec = importlib.util.spec_from_file_location(NOMBRE, ARCHIVO_S13)
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[NOMBRE] = modulo
        spec.loader.exec_module(modulo)
    return sys.modules[NOMBRE]


def _a_error(res: dict) -> dict:
    """Week 13's {"ok": False, "error": {tipo, mensaje, sugerencia}} as this Lambda's {"error", "mensaje"}."""
    e = res["error"]
    return {"error": e["tipo"], "mensaje": (e["mensaje"] + (" " + e["sugerencia"] if e.get("sugerencia") else "")).strip()}


def buscar_regla_negocio(args: dict) -> dict:
    H = semana13()
    herramientas = H.Herramientas(H.Contexto(usuario="copilot_ro", roles=[]))
    res = herramientas.llamar("buscar_regla_negocio", args)
    if not res["ok"]:
        return _a_error(res)
    por_id = {r["id"]: r for r in H.REGLAS}
    reglas = [{"id": r["id"], "nombre": por_id[r["id"]]["nombre"], "nombre_en": por_id[r["id"]]["nombre_en"],
               "definicion": por_id[r["id"]]["es"], "definition": por_id[r["id"]]["en"], "fuente": r["fuente"]}
              for r in res["reglas"]]
    salida = {"reglas": reglas}
    if res.get("sugerencia"):
        salida["sugerencia"] = res["sugerencia"]
    return salida


def muestrear_valores(args: dict, ejecutar: Callable[[str], dict]) -> dict:
    """`ejecutar` is the Lambda's ejecutar_sql (guard, read-only transaction, timeout). The column is checked against
    the data dictionary before any SQL is built, so the identifier in the query is always a known column."""
    H = semana13()
    try:
        e = H.MuestrearValores.model_validate(args or {})
    except H.ValidationError as error:
        detalle = "; ".join(f"{'.'.join(map(str, x['loc'])) or 'argumentos'}: {x['msg']}" for x in error.errors())
        return {"error": "argumentos_invalidos", "mensaje": detalle}
    columnas = H.DICCIONARIO[e.tabla]["columnas"]
    if e.columna not in columnas:
        return {"error": "columna_desconocida",
                "mensaje": f"La tabla {e.tabla} no tiene la columna {e.columna}. Columnas: {', '.join(columnas)}"}
    valores = ejecutar(f"SELECT {e.columna} AS valor, COUNT(*) AS n FROM legado.{e.tabla} "
                       f"GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {e.limite}")
    distintos = ejecutar(f"SELECT COUNT(DISTINCT {e.columna}) FROM legado.{e.tabla}")
    return {"tabla": e.tabla, "columna": e.columna, "valores_distintos": distintos["filas"][0][0],
            "valores": [{"valor": v, "filas": n} for v, n in valores["filas"]]}

