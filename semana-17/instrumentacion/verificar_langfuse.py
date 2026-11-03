"""Week 17, activity 3: LegacyBridge traces in Langfuse, end to end ($0, scripted model). Mac only (needs the activity 2 stack).

    ./semana-17/observabilidad/arrancar.sh
    cd semana-17 && uv run --group semana17 python -m instrumentacion.verificar_langfuse [--salida resultados/instrumentacion.json]

It runs four scripted tasks through the real agent loop, MCP client, OAuth-protected server and PostgreSQL, exports the
spans to the Collector (redaction, then Langfuse and the JSONL file) and reads them back from Langfuse's API:

  * the trace has as many observations as spans, with the right type (AGENT, GENERATION, TOOL, SPAN) and the same hierarchy;
  * usage and cost on each GENERATION match what the agent counted (cached tokens included);
  * the pseudonymous user is on the agent and on the server spans, failures show as ERROR;
  * no canary (prompt, SQL literal, DSN, key, token, personal data) and no `****` in Langfuse or in the Collector's file;
  * a probe of the two attribute names for cache creation (semconv `cache_creation`, util-genai `cache_write`).

The report has no secret and no local path. The salt of the user hash is random per run and is not stored.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import secrets
import sys
import time
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S17))

from instrumentacion import esquema as E  # noqa: E402
from instrumentacion.laboratorio import Laboratorio, cerrar_trazas, configurar_trazas, resumen  # noqa: E402
from instrumentacion.modelo_guionado import (  # noqa: E402
    SQL_BAJO_PUNTO_DE_REORDEN,
    TAREA,
    turnos_con_error_de_sql,
    turnos_principal,
    turnos_sin_permiso,
)

spec = importlib.util.spec_from_file_location("verificar_stack_s17", S17 / "observabilidad" / "verificar_stack.py")
vs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vs)

CANARIOS = {
    "email": "ana.garcia@example.com", "rfc": "XAXX010101000", "telefono": "55 1234 5678",
    "literal_sql": "CANARIO-SQL-77", "prompt": "CANARIO-PROMPT-ZETA",
    "dsn": "postgresql://canario:secreto-canario@db.example/inventory", "clave_api": "sk-ant-api03-CANARIOABCDEFGH",
}
TAREA_CON_CANARIOS = {**TAREA, "tarea": f"{TAREA['tarea']} Customer {CANARIOS['email']}, tax id {CANARIOS['rfc']}, "
                                         f"phone {CANARIOS['telefono']}. {CANARIOS['prompt']}"}
SQL_CON_CANARIO = SQL_BAJO_PUNTO_DE_REORDEN.replace("ORDER BY", f"AND a.art_cd <> '{CANARIOS['literal_sql']}' ORDER BY", 1)
OTLP = "http://127.0.0.1:4318/v1/traces"


def tipo_esperado(s: dict) -> str:
    """The Langfuse type that the OTLP mapping gives a span (measured: by `gen_ai.operation.name`)."""
    operacion = s["attrs"].get("gen_ai.operation.name")
    return {"invoke_agent": "AGENT", "chat": "GENERATION", "execute_tool": "TOOL"}.get(operacion, "SPAN")


def nombre_esperado(s: dict) -> str:
    """Langfuse names a TOOL observation after `gen_ai.tool.name`; every other type keeps the span name."""
    return s["attrs"]["gen_ai.tool.name"] if tipo_esperado(s) == "TOOL" else s["name"]


def estable(exp, ms=400):
    n, t0 = -1, time.time()
    while time.time() - t0 < 10:
        actual = len(exp.get_finished_spans())
        if actual == n:
            return
        n = actual
        time.sleep(ms / 1000)


def duracion_s(o: dict) -> float:
    from datetime import datetime
    f = lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))   # noqa: E731
    return (f(o["endTime"]) - f(o["startTime"])).total_seconds()


def leer_langfuse(traza: str, auth: str, minimo: int) -> list[dict]:
    return vs.observaciones(traza, auth, espera=120, minimo=minimo)


def sonda_cache(tracer_provider) -> dict:
    """Two synthetic generations: one reports cache creation as `cache_creation` (semconv), the other as `cache_write`
    (util-genai 1.3b0). Reads back what Langfuse stored."""
    tr = tracer_provider.get_tracer("sonda-cache")
    trazas = {}
    for nombre, clave in (("semconv", "gen_ai.usage.cache_creation.input_tokens"),
                          ("util_genai", "gen_ai.usage.cache_write.input_tokens")):
        with tr.start_as_current_span("chat claude-haiku-5-5", attributes={
                "gen_ai.operation.name": "chat", "gen_ai.provider.name": "anthropic", "gen_ai.request.model": "claude-haiku-5-5",
                "gen_ai.usage.input_tokens": 1000, "gen_ai.usage.output_tokens": 10,
                "gen_ai.usage.cache_read.input_tokens": 300, clave: 200}) as s:
            trazas[nombre] = format(s.get_span_context().trace_id, "032x")
    return trazas


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=str(S17 / "resultados" / "instrumentacion.json"))
    a = ap.parse_args(argv)
    if vs.peticion("http://127.0.0.1:3100/api/public/health")[0] != 200 or vs.peticion("http://127.0.0.1:13133/")[0] != 200:
        print("[verificar] the stack is not up: run semana-17/observabilidad/arrancar.sh first", file=sys.stderr)
        return 2
    auth = vs.auth_langfuse()
    os.environ["LAB_OBS_SALT"] = secrets.token_hex(16)
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "NO_CONTENT"
    E.ESTRICTO = True
    exp = configurar_trazas(otlp_http=OTLP)
    from instrumentacion.laboratorio import _PROVEEDOR

    corridas = {}
    with Laboratorio(tenant="lab") as lab:
        def correr(nombre, turnos, **kw):
            exp.clear()
            r, modelo, cliente = lab.correr(turnos, **kw)
            estable(exp)
            spans = resumen(exp.get_finished_spans())
            raiz = next(s for s in spans if s["name"].startswith("invoke_agent"))
            corridas[nombre] = {"resultado": r, "spans": [s for s in spans if s["trace"] == raiz["trace"]], "raiz": raiz,
                                "cliente": cliente}
            print(f"[verificar] {nombre}: {r.estado}, {len(corridas[nombre]['spans'])} spans")

        correr("principal", turnos_principal(sql=SQL_CON_CANARIO), tarea=TAREA_CON_CANARIOS)
        correr("error_sql", turnos_con_error_de_sql())
        correr("sin_permiso", turnos_sin_permiso(), usuario="almacenista",
               catalogo_obsoleto={"legado__proponer_orden_compra": ("legado", "proponer_orden_compra")})
        correr("api_falla", turnos_principal(), modelo_falla=1,
               mensaje_de_falla=f"boom {CANARIOS['dsn']} {CANARIOS['clave_api']} {CANARIOS['email']}")
        tokens = list(lab.entorno._tokens.values())
        from psycopg.conninfo import conninfo_to_dict
        clave_db = conninfo_to_dict(os.environ["NLQ_LEGADO_DSN"]).get("password")
    sondas = sonda_cache(_PROVEEDOR["proveedor"])
    cerrar_trazas()

    privados = {**CANARIOS, "token": tokens, "clave_db": [clave_db], "sujeto": ["sub-analista", "sub-almacenista"]}
    informe = {"fecha": time.strftime("%Y-%m-%d"), "plataforma": platform.platform(terse=True), "modelo": "guionado (sin API, $0)",
               "escenarios": {}, "sondas": {}}
    todo_ok = True
    textos_langfuse = []
    for nombre, c in corridas.items():
        spans, r = c["spans"], c["resultado"]
        obs = leer_langfuse(c["raiz"]["trace"], auth, len(spans))
        por_id = {o["id"]: o for o in obs}
        textos_langfuse.append(json.dumps(obs, default=str))
        ids_ok = all(s["span"] in por_id for s in spans)
        tipos_ok = ids_ok and all(por_id[s["span"]]["type"] == tipo_esperado(s) for s in spans)
        nombres_ok = ids_ok and all(por_id[s["span"]]["name"] == nombre_esperado(s) for s in spans)
        jerarquia_ok = ids_ok and all((por_id[s["span"]].get("parentObservationId") or None) == s["parent"] for s in spans)
        con_error = sorted(f"{por_id[s['span']]['type']} {por_id[s['span']]['name']}" for s in spans
                           if ids_ok and por_id[s["span"]]["level"] == "ERROR")
        # level and status of every span as the lab recorded it (ERROR spans must be ERROR in Langfuse, the rest DEFAULT)
        nivel_ok = ids_ok and all((por_id[s["span"]]["level"] == "ERROR") == (s["estado"] == "ERROR") for s in spans)
        generaciones = [por_id[s["span"]] for s in spans if s["name"].startswith("chat ") and ids_ok and s["estado"] != "ERROR"]
        usos = [g["usageDetails"] for g in generaciones]
        agente = c["raiz"]["attrs"]
        lectura = sum(u.get("input_cached_tokens", 0) for u in usos)
        creacion = sum(u.get("input_cache_creation", 0) for u in usos)
        uso_ok = (bool(usos) and sum(u["input"] for u in usos) == agente["lab.run.tokens.input"]
                  and sum(u["output"] for u in usos) == agente["lab.run.tokens.output"]
                  and lectura == agente["lab.run.tokens.cache_read"] and creacion == agente["lab.run.tokens.cache_creation"]
                  and all(u["total"] == u["input"] + u["output"] + u.get("input_cached_tokens", 0) + u.get("input_cache_creation", 0)
                          for u in usos))
        costo = sum(g["costDetails"]["total"] for g in generaciones)
        costo_ok = bool(generaciones) and abs(costo - agente["lab.run.cost_usd"]) < 1e-7
        usuario_ok = (por_id[c["raiz"]["span"]].get("userId") == agente["user.id"] == E.seudonimo(
            "sub-almacenista" if nombre == "sin_permiso" else "sub-analista")) if ids_ok else False
        usuarios_servidor = sorted({o.get("userId") for o in obs if o["name"] in ("authorize",) or o["name"].startswith("handle_tool")})
        usuario_servidor_ok = usuarios_servidor == [agente["user.id"]] if any(
            s["name"] == "authorize" or s["name"].startswith("handle_tool") for s in spans) else True
        duraciones = [(duracion_s(por_id[s["span"]]), (s["fin"] - s["inicio"]) / 1e9) for s in spans
                      if ids_ok and s["name"].startswith("chat ")]
        minimos = {"principal": (0.05, 0.08, 0.06)}.get(nombre, ())      # scripted latency of each turn (modelo_guionado.py)
        latencia_ok = bool(duraciones) and all(abs(lf - otel) < 0.005 for lf, otel in duraciones) and all(
            otel >= m for (_, otel), m in zip(sorted(duraciones, key=lambda d: d[1]), sorted(minimos)))
        sin_contenido = all(o.get("input") is None and o.get("output") is None for o in obs)
        # in `api_falla` the second model call fails before it reports usage: the totals are those of the call that finished
        ok = all([len(obs) == len(spans), ids_ok, tipos_ok, nombres_ok, jerarquia_ok, nivel_ok, uso_ok, costo_ok,
                  usuario_ok, usuario_servidor_ok, sin_contenido, latencia_ok])
        informe["escenarios"][nombre] = {
            "estado_agente": r.estado, "spans": len(spans), "observaciones": len(obs), "ids_iguales": ids_ok,
            "tipos_correctos": tipos_ok, "nombres_correctos": nombres_ok, "jerarquia_igual": jerarquia_ok,
            "niveles_error_correctos": nivel_ok, "uso_igual_al_del_agente": uso_ok, "costo_igual_al_del_agente": costo_ok,
            "usuario_seudonimo_en_el_agente": usuario_ok, "usuario_seudonimo_en_el_servidor": usuario_servidor_ok,
            "sin_input_ni_output": sin_contenido, "latencia_de_langfuse_igual_a_la_del_span": latencia_ok, "ok": bool(ok),
            "tipos": sorted({o["type"] for o in obs}), "observaciones_con_error": con_error,
            "generaciones": [{"uso": g["usageDetails"], "costo": g["costDetails"], "modelo": g["model"],
                              "duracion_s": round(duracion_s(g), 3)} for g in generaciones]}
        todo_ok = todo_ok and bool(ok)

    # canaries and false positives: Langfuse and the Collector's file, for every trace of the run
    trazas = {c["raiz"]["trace"] for c in corridas.values()}
    archivo = vs.DATOS / "trazas.jsonl"
    texto_archivo = archivo.read_text() if archivo.exists() else ""
    en_archivo = sorted(t for t in trazas if t in texto_archivo)
    lineas_archivo = [l for l in texto_archivo.splitlines() if any(t in l for t in trazas)]
    texto_total = "\n".join(textos_langfuse) + "\n" + "\n".join(lineas_archivo)
    visto = sorted(k for k, v in privados.items() if any(x in texto_total for x in (v if isinstance(v, list) else [v])))
    informe["privacidad"] = {"canarios_en_langfuse_o_archivo": visto, "asteriscos_en_langfuse_o_archivo": "****" in texto_total,
                             "trazas_en_el_archivo": len(en_archivo), "trazas_de_la_corrida": len(trazas),
                             "ok": not visto and "****" not in texto_total and len(en_archivo) == len(trazas)}
    todo_ok = todo_ok and informe["privacidad"]["ok"]

    # probe: which attribute name does Langfuse understand for cache creation?
    for nombre, traza in sondas.items():
        obs = leer_langfuse(traza, auth, 1)
        informe["sondas"][nombre] = {"usageDetails": obs[0]["usageDetails"] if obs else None}
    semconv = informe["sondas"]["semconv"]["usageDetails"] or {}
    util = informe["sondas"]["util_genai"]["usageDetails"] or {}
    informe["sondas"]["conclusion"] = {
        "semconv_cache_creation_se_entiende": semconv.get("input_cache_creation") == 200,
        "util_genai_cache_write_se_entiende": util.get("input_cache_creation") == 200 or util.get("input_cache_write") == 200}
    informe["ok"] = bool(todo_ok and informe["sondas"]["conclusion"]["semconv_cache_creation_se_entiende"])
    Path(a.salida).write_text(json.dumps(informe, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in informe.items() if k in ("ok", "privacidad", "sondas")}, indent=1)[:1500])
    for n, e in informe["escenarios"].items():
        print(n, "ok" if e["ok"] else "FALLA", {k: v for k, v in e.items() if v is False})
    return 0 if informe["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
