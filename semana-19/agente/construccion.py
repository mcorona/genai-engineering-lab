"""Week 19, activity 6: binds the agent request path (agente/handler.py) to the real parts.

- The loop is the week 13 one, loaded from its file. Its package names (`agente`, `herramientas`) are the same as this
  lab's own, so they are isolated while it loads and restored afterwards.
- The model: Bedrock Converse through agente/modelo.py (`modelo.invocar`, week 20's seam) and agente/converse_adaptador.py, with the guardrail of the activity 5 version from the
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
from agente import modelo
from agente.presupuesto import Precios
from agente.sumidero_logs import SumideroCloudWatch
from herramientas import contrato  # the internal call of the tools Lambda (one contract for its three callers)
from presupuestos.politica import Limite, Politica

RAIZ = Path(__file__).resolve().parents[2]
# The week 13 loop: the repository folder, or the asset folder of the agent Lambda (infra/paquete_agente.py sets it).
S13 = Path(os.environ.get("S19_RUTA_SEMANA13", RAIZ / "semana-13"))
# Equal to ia/config.py's MODELO_ID: ia/ is not in the Lambda package, so it is repeated here (test_agente_modelo.py).
# Week 20, activity 2: the system profile the agent's application profile copies; the Lambda calls what the stack puts
# in MODELO (the application profile's ARN, or this id when ia/config.py turns the profile off).
MODELO_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
MODELO = "MODELO"     # the model id or inference profile ARN the agent calls (set by the stack, from ia/config.py)
FUNCION_HERRAMIENTAS = "FUNCION_HERRAMIENTAS"     # environment variable names (no defaults: fail closed)
GUARDRAIL_ID = "GUARDRAIL_ID"
GUARDRAIL_VERSION = "GUARDRAIL_VERSION"
GRUPO_SPANS = "GRUPO_SPANS"      # CloudWatch Logs group of the span lines (set by the stack)
CAMINO_HERRAMIENTAS = "CAMINO_HERRAMIENTAS"   # activity 7: directo (lambda.invoke, default) | gateway (MCP)
GATEWAY_URL = "GATEWAY_URL"      # the gateway's MCP endpoint, required when the path is gateway
CAMINOS = ("directo", "gateway")
PRESUPUESTO_TAREA = "PRESUPUESTO_TAREA"   # week 20: semana17 (default, week 17 calibration) | techo_semana20
PRESUPUESTOS = ("semana17", "techo_semana20")

_PRESUPUESTO_TAREA_HAIKU55 = {"usd": 0.0063, "tokens": 46000}   # week 17 calibration (semana-17/presupuestos/politica_calibrada.json)
_RAZON_PRECIO = 1.1 / 0.1     # Haiku 4.5 over Haiku 5.5 in week 7's table, input and output alike
# Week 20, activity 1 (Manuel's OK of 2026-11-23): a per-task ceiling above every week 19 task (at most 0.063 USD and
# 43,616 tokens), so the corrected run is not cut by the budget and its spend is Haiku 4.5's own distribution. The new
# calibrated limit is set from that run; this ceiling is not a calibration.
_TECHO_SEMANA20 = {"usd": 0.12, "tokens": 100_000}
PRECIOS = Precios(entrada_1m=1.1, salida_1m=5.5)   # Haiku 4.5, USD per million tokens (week 7's table)
# Week 20, activity 3: the cache prices of Haiku 4.5, regional (the us. profile), from the Price List
# (semana-20/resultados/linea_base.md §4.1): read 0.11, write 1.375 with the 5-minute TTL and 2.20 with 1 hour.
CACHE_PROMPT = "CACHE_PROMPT"   # environment variable, set by the stack: one of MODOS_CACHE (absent: the default)
CACHE_TTL = "CACHE_TTL"         # 5m | 1h (absent: the default)
MODOS_CACHE = modelo.MODOS_CACHE
TTLS_CACHE = modelo.TTLS_CACHE
CACHE_PROMPT_POR_OMISION = "off"   # equal to ia/config.py CACHE_PROMPT and CACHE_TTL (test_agente_cache.py)
CACHE_TTL_POR_OMISION = "5m"
_CACHE_ESCRITURA_1M = {"5m": 1.375, "1h": 2.2}
_CACHE_LECTURA_1M = 0.11


def precios(ttl: str = "5m") -> Precios:
    return Precios(entrada_1m=PRECIOS.entrada_1m, salida_1m=PRECIOS.salida_1m, cache_lectura_1m=_CACHE_LECTURA_1M,
                   cache_escritura_1m=_CACHE_ESCRITURA_1M[ttl])


# Week 20, activity 4, R1: the router's values, equal to ia/config.py (test_agente_ruteo_config.py; ADR 0015).
RUTEO = "RUTEO"                  # environment variable, set by the stack: one of MODOS_RUTEO (absent: the default)
MODOS_RUTEO = ("off", "r1")
RUTEO_POR_OMISION = "off"
NOVA_LITE = "us.amazon.nova-lite-v1:0"
SONNET_46 = "us.anthropic.claude-sonnet-4-6"
RUTEO_CANDIDATOS = (NOVA_LITE, MODELO_ID, SONNET_46)
RUTEO_REGLAS = {
    "senales": ("error_herramienta", "resultado_vacio", "bloqueo_capa", "respuesta_invalida", "presion_pasos",
                "presion_tokens", "respuesta_vacia", "abstencion", "idioma"),
    "alcance": "resto_de_la_tarea",
    "max_escalamientos": 2,
    "pasos_presion": 7,
    "tokens_presion": 50_000,
}
CACHE_POR_MODELO = {NOVA_LITE: "historial+sistema", MODELO_ID: "historial", SONNET_46: "historial+sistema"}
# Nova takes only the 5-minute TTL, and the ttl field must be omitted for it (prompt-caching docs, read 2026-11-27).
TTLS_POR_MODELO = {NOVA_LITE: ("5m",), MODELO_ID: TTLS_CACHE, SONNET_46: TTLS_CACHE}
# Each candidate's prices with the 5-minute TTL, USD per million tokens, regional (the us. profile), from the Price
# List (semana-20/resultados/precios.json, 2026-11-23): input, output, cache read, cache write. The router's budget
# prices each call at the model that served it.
SKUS_POR_MODELO = {
    NOVA_LITE: ("QRGWJ3P8FT28EYX2", "CBZ6A6U7XK8WJ3KA", "FYTFBAWEJFBAVTWK", "NF8UDYEDB4HXGNAZ"),
    MODELO_ID: ("JQDUC8Q4K8C6GSGH", "X629GDA2GXAP6R54", "VJXPZKPF7EDCFXN3", "CDG7WESKYQ9N9KDN"),
    SONNET_46: ("KPFGPZJ8VWMREGAV", "GMB9AQ5DYNAGYZEC", "2459RQS6BSFATF92", "UZUVWF3P26ENQTZ8"),
}
PRECIOS_POR_MODELO = {
    NOVA_LITE: Precios(entrada_1m=0.06, salida_1m=0.24, cache_lectura_1m=0.015, cache_escritura_1m=0.0),
    MODELO_ID: precios("5m"),
    SONNET_46: Precios(entrada_1m=3.3, salida_1m=16.5, cache_lectura_1m=0.33, cache_escritura_1m=4.125),
}


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


def cargar_de_semana13(relativo: str, nombre: str):
    """A week 13 module, from its file, with its own imports resolved inside the isolation."""
    with _aislado():
        spec = importlib.util.spec_from_file_location(nombre, S13 / relativo)
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[nombre] = modulo
        spec.loader.exec_module(modulo)
    return modulo


def cargar_bucle_semana13():
    """The week 13 Agente class, from its file, with its own imports resolved inside the isolation."""
    modulo = cargar_de_semana13("agente/loop.py", "bucle_semana13")
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


def presupuesto(entorno) -> str:
    """The per-task budget in use. Unknown values are an error, never a silent fall back to the default."""
    valor = entorno.get(PRESUPUESTO_TAREA) or "semana17"
    if valor not in PRESUPUESTOS:
        raise RuntimeError(f"{PRESUPUESTO_TAREA} desconocido: {valor}")
    return valor


def politica_de_la_tarea(entorno=None) -> Politica:
    if presupuesto(os.environ if entorno is None else entorno) == "techo_semana20":
        return Politica(tarea=Limite(**_TECHO_SEMANA20))
    tope = _PRESUPUESTO_TAREA_HAIKU55
    return Politica(tarea=Limite(usd=round(tope["usd"] * _RAZON_PRECIO, 6), tokens=tope["tokens"]))


def cache(entorno) -> tuple[str, str]:
    """(mode, TTL) of prompt caching. Unknown values are an error, never a silent fall back to the default."""
    modo = entorno.get(CACHE_PROMPT) or CACHE_PROMPT_POR_OMISION
    ttl = entorno.get(CACHE_TTL) or CACHE_TTL_POR_OMISION
    if modo not in MODOS_CACHE:
        raise RuntimeError(f"{CACHE_PROMPT} desconocido: {modo}")
    if ttl not in TTLS_CACHE:
        raise RuntimeError(f"{CACHE_TTL} desconocido: {ttl}")
    return modo, ttl


def camino(entorno) -> str:
    """The tools path. Unknown values are an error, never a silent fall back to the default."""
    valor = entorno.get(CAMINO_HERRAMIENTAS) or "directo"
    if valor not in CAMINOS:
        raise RuntimeError(f"{CAMINO_HERRAMIENTAS} desconocido: {valor}")
    return valor


def exigir_entorno(entorno) -> None:
    requeridas = [MODELO, FUNCION_HERRAMIENTAS, GUARDRAIL_ID, GUARDRAIL_VERSION, GRUPO_SPANS]
    if camino(entorno) == "gateway":
        requeridas.append(GATEWAY_URL)
    faltan = [n for n in requeridas if not entorno.get(n)]
    if faltan:
        raise RuntimeError(f"faltan variables de entorno: {', '.join(faltan)}")


def construir(*, cliente_converse, cliente_lambda, entorno=None, exportar=None, cliente_logs=None,
              flujo_spans: str = "agente", token: str | None = None, abrir_mcp=None) -> dict:
    """The collaborators of agente.handler.tratar_pregunta. Missing environment is an error, not a default.
    `token` is the user's access token (only the gateway path uses it); `abrir_mcp` replaces the MCP session in tests."""
    entorno = os.environ if entorno is None else entorno
    exigir_entorno(entorno)
    via = camino(entorno)
    guardrail = {"guardrailIdentifier": entorno[GUARDRAIL_ID], "guardrailVersion": entorno[GUARDRAIL_VERSION]}
    Agente, _ = cargar_bucle_semana13()

    def llamar_converse(req: dict) -> dict:
        return cliente_converse.converse(**req)

    modo_cache, ttl = cache(entorno)
    api = modelo.api(llamar_converse, config=modelo.ConfigModelo(modelo_id=entorno[MODELO], guardrail=guardrail,
                                                                 cache=modo_cache, ttl=ttl))
    cerrar = None
    if via == "gateway":
        from agente.cliente_gateway import LlamadorGateway
        llamar_real = LlamadorGateway(entorno[GATEWAY_URL], token, al_contrato=_al_contrato_semana13, abrir=abrir_mcp)
        cerrar = llamar_real.cerrar
    else:
        llamar_real = llamador_de_herramientas(cliente_lambda, entorno[FUNCION_HERRAMIENTAS])
    definiciones = C.definiciones_semana19()
    return {
        "agente_factory": lambda api_envuelta, herramientas: Agente(herramientas, modelo="claude-haiku-4-5-20251001",
                                                                    esfuerzo="low", api=api_envuelta),
        "llamar_herramienta": llamar_real,
        "definiciones": definiciones,
        "api_modelo": api,
        "politica": politica_de_la_tarea(entorno),
        "precios": precios(ttl),
        "exportar": exportar or SumideroCloudWatch(cliente_logs, entorno[GRUPO_SPANS], flujo_spans),
        "camino": via,
        "cerrar": cerrar,
    }
