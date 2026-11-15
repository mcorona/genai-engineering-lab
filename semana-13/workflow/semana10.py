"""Week 13, activity 6: the week 10 assistant as a fixed-routing workflow, over the task gold set.

Fixed steps, in code (not decided by the model), with the same components as week 10:
1. Routing: `ruteo.clasificar` (Haiku 5.5 low, the prompt of week 10's activity 6) → sql, documental or mixta.
2. sql or mixed route: the week 10 NLQ tool (Haiku 5.5 low, the legacy DDL + the full dictionary, the NO_SQL
   abstention) generates ONE query per output key, which runs once with week 13's ejecutar_sql tool
   (guard and read-only transaction). No retries and no rule lookups, as in week 10.
3. Document route: week 10 would answer with the document index, which produces no SQL or computed figures; for this
   gold set (every answer comes from the database) it is recorded as an abstention.

Adaptations, so that only the orchestration is compared: the NLQ receives the same output information as the agent (the
description of each key and the shape contract, FORMA), and in tasks with several keys there is one call per key.
The workflow cannot ask for a clarification: it has no such step.
"""
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parents[1]
REPO = AQUI.parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(REPO / "semana-10" / "experimentos"))

import ruteo  # noqa: E402
import sql_legado as sl  # noqa: E402

from agente.loop import FORMA, api_anthropic, costo  # noqa: E402

HAIKU = "claude-haiku-5-5"
ABSTENCION = ("\n\nIf the schema and dictionary do not contain the data the question asks for (for example service "
              "levels, freight rates, policies, approvals, warehouse layouts or documents), do not approximate it with "
              "other columns: output exactly NO_SQL instead of a query.")  # identical to semana-10/experimentos/asistente.py
SIS_NLQ = sl.sistema("\n".join(sl.DDL_LEGADO[t] for t in sl.DICCIONARIO), sl.texto_diccionario(list(sl.DICCIONARIO))) + ABSTENCION


def nlq(pregunta: str):
    t0 = time.perf_counter()
    d = api_anthropic({"model": HAIKU, "max_tokens": 8000, "system": SIS_NLQ, "output_config": {"effort": "low"},
                       "messages": [{"role": "user", "content": pregunta}]})
    texto = "".join(b.get("text", "") for b in d["content"] if b.get("type") == "text")
    u = d["usage"]
    return texto, u["input_tokens"], u["output_tokens"], time.perf_counter() - t0


def resolver(tarea: dict, h) -> dict:
    """Returns the same format as the agent: state, final (RespuestaFinal), steps, tokens, cost, seconds."""
    t0 = time.perf_counter()
    r = ruteo.clasificar(HAIKU, "low", tarea["tarea"])
    tin, tout, llamadas, pasos = r["tokens_in"], r["tokens_out"], [], 1
    ruta = r["ruta"] or "sql"
    if ruta == "documental":
        final = {"estado": "abstenida", "respuesta": "Ruta documental: el workflow no calcula cifras sobre la base para esta pregunta.",
                 "resultados": [], "evidencia": [], "supuestos": [], "pregunta_aclaracion": None}
        estado = "abstenida"
    else:
        resultados, abstuvo = [], False
        salida = tarea.get("salida") or {"respuesta": {"descripcion": "the answer", "tipo": "filas"}}
        for clave, s in salida.items():
            pregunta = (tarea["tarea"] + f"\n\nReturn only: {s['descripcion']} ({s['tipo']}).\n\n" + FORMA)
            texto, i, o, _ = nlq(pregunta)
            tin, tout, pasos = tin + i, tout + o, pasos + 1
            if texto.strip().upper().startswith("NO_SQL"):
                abstuvo = True
                break
            consulta = sl.re7.extraer_sql(texto)
            if consulta is None:
                continue
            res = h.llamar("ejecutar_sql", {"sql": consulta, "max_filas": 200})
            llamadas.append({"clave": clave, "ok": res["ok"], "error": (res.get("error") or {}).get("tipo")})
            valor = [f if len(f) > 1 else f[0] for f in res["filas"]] if res["ok"] else None
            if res["ok"] and len(res["filas"]) == 1 and len(res["filas"][0]) == 1:
                valor = res["filas"][0][0]
            resultados.append({"clave": clave, "sql": consulta, "valor": valor})
        if abstuvo:
            estado = "abstenida"
            final = {"estado": estado, "respuesta": "NO_SQL: los datos no están en el esquema.", "resultados": [],
                     "evidencia": [], "supuestos": [], "pregunta_aclaracion": None}
        else:
            estado = "respondida"
            final = {"estado": estado, "respuesta": "", "resultados": resultados if tarea.get("salida") else [],
                     "evidencia": [], "supuestos": [], "pregunta_aclaracion": None}
    return {"estado": estado, "final": final, "ruta": ruta, "pasos": pasos, "herramientas": len(llamadas),
            "errores_herramienta": sum(not x["ok"] for x in llamadas), "tokens_in": tin, "tokens_out": tout,
            "costo_usd": costo(HAIKU, tin, tout), "segundos": round(time.perf_counter() - t0, 2)}
