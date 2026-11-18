"""Week 19, activity 6: binds the agent request path (agente/handler.py) to the real parts.

- The loop is the week 13 one, loaded from its file. Its package names (`agente`, `herramientas`) are the same as this
  lab's own, so they are isolated while it loads and restored afterwards.
- The model: Bedrock Converse through agente/converse_adaptador.py, with the guardrail of the activity 5 version from the
  environment (fail closed: no default).
- The tools: the tools Lambda, invoked by name with the payload shape its handler reads.
- Budget: week 17's calibrated task cap, with the USD part converted from Haiku 5.5 to Haiku 4.5 prices (a x11 ratio
  from week 7's table). GAP: that USD cap is derived, not calibrated for Haiku 4.5.
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import sys
from pathlib import Path

from agente import capa_determinista as C
from agente.converse_adaptador import api_converse
from agente.presupuesto import Precios
from agente.sumidero_logs import SumideroCloudWatch
from herramientas import contrato  # the internal call of the tools Lambda (one contract for its three callers)
from presupuestos.politica import Limite, Politica

RAIZ = Path(__file__).resolve().parents[2]
# The week 13 loop: the repository folder, or the asset folder of the agent Lambda (infra/paquete_agente.py sets it).
S13 = Path(os.environ.get("S19_RUTA_SEMANA13", RAIZ / "semana-13"))
MODELO_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
FUNCION_HERRAMIENTAS = "FUNCION_HERRAMIENTAS"     # environment variable names (no defaults: fail closed)
GUARDRAIL_ID = "GUARDRAIL_ID"
GUARDRAIL_VERSION = "GUARDRAIL_VERSION"
GRUPO_SPANS = "GRUPO_SPANS"      # CloudWatch Logs group of the span lines (set by the stack)

_PRESUPUESTO_TAREA_HAIKU55 = {"usd": 0.0063, "tokens": 46000}   # week 17 calibration (semana-17/presupuestos/politica_calibrada.json)
_RAZON_PRECIO = 1.1 / 0.1     # Haiku 4.5 over Haiku 5.5 in week 7's table, input and output alike


def _es_del_nombre(nombre: str, prefijos: tuple[str, ...]) -> bool:
    return any(nombre == p or nombre.startswith(p + ".") for p in prefijos)


@contextlib.contextmanager
def _aislado(prefijos=("agente", "herramientas")):
    """Removes the lab's own `agente` and `herramientas` from sys.modules and puts week 13's in front, then restores."""
    guardados = {k: v for k, v in sys.modules.items() if _es_del_nombre(k, prefijos)}
    for k in guardados:
        del sys.modules[k]
    ruta_previa = list(sys.path)
    sys.path.insert(0, str(S13))
    try:
        yield
    finally:
        sys.path[:] = ruta_previa
        for k in [k for k in sys.modules if _es_del_nombre(k, prefijos)]:
            del sys.modules[k]
        sys.modules.update(guardados)


def cargar_bucle_semana13():
    """The week 13 Agente class, from its file, with its own imports resolved inside the isolation."""
    with _aislado():
        spec = importlib.util.spec_from_file_location("bucle_semana13", S13 / "agente" / "loop.py")
        modulo = importlib.util.module_from_spec(spec)
        sys.modules["bucle_semana13"] = modulo
        spec.loader.exec_module(modulo)
    return modulo.Agente, modulo


def llamador_de_herramientas(cliente_lambda, nombre_funcion: str):
    def llamar(nombre: str, args: dict, solicitante: str | None = None) -> dict:
        carga = json.dumps(contrato.entrada_de_herramienta(nombre, args, solicitante), ensure_ascii=False).encode("utf-8")
        resp = cliente_lambda.invoke(FunctionName=nombre_funcion, Payload=carga)
        cuerpo = json.loads(resp["Payload"].read())
        return _al_contrato_semana13(cuerpo, fallo=bool(resp.get("FunctionError")))
    return llamar


def _al_contrato_semana13(cuerpo, *, fallo: bool) -> dict:
    """The tools Lambda answers {"filas": ...} or {"error": kind, "mensaje": ...}; the week 13 loop reads `ok` (a result
    without it counts as a tool error and, three in a row, stops the run). A failed function (import, timeout, unhandled
    error) becomes a closed error: the runtime's message and trace never reach the model; operators read them in the
    tools function's own log group."""
    if fallo or not isinstance(cuerpo, dict):
        return {"ok": False, "error": {"tipo": "herramienta_no_disponible", "mensaje": "La herramienta no respondió.",
                                       "sugerencia": "Responde con lo que ya tengas o indica que no fue posible."}}
    if "error" in cuerpo:
        return {"ok": False, "error": {"tipo": str(cuerpo["error"]), "mensaje": str(cuerpo.get("mensaje", ""))[:800]}}
    return {"ok": True, **cuerpo}


def politica_de_la_tarea() -> Politica:
    tope = _PRESUPUESTO_TAREA_HAIKU55
    return Politica(tarea=Limite(usd=round(tope["usd"] * _RAZON_PRECIO, 6), tokens=tope["tokens"]))


def exigir_entorno(entorno) -> None:
    faltan = [n for n in (FUNCION_HERRAMIENTAS, GUARDRAIL_ID, GUARDRAIL_VERSION, GRUPO_SPANS) if not entorno.get(n)]
    if faltan:
        raise RuntimeError(f"faltan variables de entorno: {', '.join(faltan)}")


def construir(*, cliente_converse, cliente_lambda, entorno=None, exportar=None, cliente_logs=None,
              flujo_spans: str = "agente") -> dict:
    """The collaborators of agente.handler.tratar_pregunta. Missing environment is an error, not a default."""
    entorno = os.environ if entorno is None else entorno
    exigir_entorno(entorno)
    guardrail = {"guardrailIdentifier": entorno[GUARDRAIL_ID], "guardrailVersion": entorno[GUARDRAIL_VERSION]}
    Agente, _ = cargar_bucle_semana13()

    def llamar_converse(req: dict) -> dict:
        return cliente_converse.converse(**req)

    api = api_converse(llamar_converse, modelo_id=MODELO_ID, guardrail=guardrail)
    llamar_real = llamador_de_herramientas(cliente_lambda, entorno[FUNCION_HERRAMIENTAS])
    definiciones = C.definiciones_semana19()
    return {
        "agente_factory": lambda api_envuelta, herramientas: Agente(herramientas, modelo="claude-haiku-4-5-20251001",
                                                                    esfuerzo="low", api=api_envuelta),
        "llamar_herramienta": llamar_real,
        "definiciones": definiciones,
        "api_modelo": api,
        "politica": politica_de_la_tarea(),
        "precios": Precios(entrada_1m=1.1, salida_1m=5.5),
        "exportar": exportar or SumideroCloudWatch(cliente_logs, entorno[GRUPO_SPANS], flujo_spans),
    }
