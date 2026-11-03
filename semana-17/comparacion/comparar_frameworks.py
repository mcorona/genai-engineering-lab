"""Week 17, activity 3 (optional): the same task through the lab's instrumentation, Strands and LangGraph ($0, scripted model).

    cd semana-17 && uv run --group semana17 python comparacion/comparar_frameworks.py [--langfuse] [--salida resultados/frameworks.json]

The lab's real MCP server (OAuth boundary, PostgreSQL) serves all three. The model is scripted, the same turns for each. What is
compared is what each one traces by itself, with nothing configured but a TracerProvider:

  * the span tree, and whether the agent's trace continues into the server's spans;
  * which attributes it emits against the locked shape (`instrumentacion/esquema.py`), and under which names;
  * how it counts tokens (total or uncached input, where the cache goes);
  * what content it records: the prompt, the SQL, the returned rows, the token.

`--langfuse` (Mac only, needs the stack of activity 2) also exports the Strands trace and the lab's spans through the Collector and
reads back what Langfuse made of them. The report has no secret and no local path; the salt of the keyed hashes is random per run.
Strands runs in the `st` venv of week 15 and LangGraph in `lg`; `VENVS_S15` overrides their location.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
S15 = S17.parent / "semana-15"
VENVS = Path(os.environ.get("VENVS_S15", S15 / ".venvs"))
sys.path.insert(0, str(S17))

from instrumentacion import esquema as E  # noqa: E402
from instrumentacion.laboratorio import Laboratorio, cerrar_trazas, configurar_trazas, resumen  # noqa: E402
from instrumentacion.modelo_guionado import SQL_BAJO_PUNTO_DE_REORDEN, TAREA, turnos_principal  # noqa: E402

MODELO = "claude-haiku-5-5"
OTLP = "http://127.0.0.1:4318/v1/traces"
CANARIOS = {
    "email": "ana.garcia@example.com", "rfc": "XAXX010101000", "telefono": "55 1234 5678",
    "literal_sql": "CANARIO-SQL-77", "prompt": "CANARIO-PROMPT-ZETA",
}
TEXTO_TAREA = (f"{TAREA['tarea']} Customer {CANARIOS['email']}, tax id {CANARIOS['rfc']}, phone {CANARIOS['telefono']}. "
               f"{CANARIOS['prompt']}")
SQL = SQL_BAJO_PUNTO_DE_REORDEN.replace("ORDER BY", f"AND a.art_cd <> '{CANARIOS['literal_sql']}' ORDER BY", 1)


def cargar_stack():
    spec = importlib.util.spec_from_file_location("verificar_stack_s17", S17 / "observabilidad" / "verificar_stack.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def guion() -> dict:
    """The lab's main scenario as data. MCP tool names are the server's own (no `legado__` prefix) for the frameworks."""
    return json.loads(json.dumps({"modelo": MODELO, "tarea": TEXTO_TAREA, "sql": SQL, "canarios": CANARIOS,
                                  "turnos": turnos_principal(prefijo="", sql=SQL)}))


def estable(exp, ms=400):
    n, t0 = -1, time.time()
    while time.time() - t0 < 10:
        actual = len(exp.get_finished_spans())
        if actual == n:
            return
        n = actual
        time.sleep(ms / 1000)


def lanzar(venv: str, script: str, tmp: Path, url: str, token: str, otlp: str | None = None, extra: dict | None = None) -> dict:
    """Runs a framework script in its venv. The token goes in the environment, never in the arguments."""
    salida = tmp / f"{venv}-{len(list(tmp.glob(venv + '-*.json')))}.json"
    env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", ""), "LANG": "C.UTF-8",
           "LAB_GUION": str(tmp / "guion.json"), "LAB_MCP_URL": url, "LAB_TOKEN": token, "LAB_SALIDA": str(salida)}
    if otlp:
        env["LAB_OTLP_HTTP"] = otlp
    env.update(extra or {})
    py = VENVS / venv / "bin" / "python"
    p = subprocess.run([str(py), str(S17 / "comparacion" / script)], env=env, capture_output=True, text=True, timeout=240)
    if p.returncode or not salida.exists():
        tail = (p.stderr or p.stdout)[-1500:].replace(token, "<token>")
        raise SystemExit(f"{script} failed (exit {p.returncode}):\n{tail}")
    return json.loads(salida.read_text(encoding="utf-8"))


# ---------- analysis ----------

def operacion(s: dict) -> str:
    return s["attrs"].get("gen_ai.operation.name") or s["name"]


def por_operacion(spans: list[dict]) -> dict[str, dict]:
    grupos: dict[str, list[dict]] = {}
    for s in spans:
        grupos.setdefault(operacion(s), []).append(s)
    return {op: {"spans": len(g), "claves": sorted({k for s in g for k in s["attrs"]}),
                 "eventos": sorted({e["name"] for s in g for e in s["eventos"]})} for op, g in sorted(grupos.items())}


TIPO_LAB = {"invoke_agent": "invoke_agent", "chat": "chat", "execute_tool": "execute_tool"}


def cobertura(grupos: dict[str, dict]) -> dict:
    """Per operation: which of the framework's keys the locked shape accepts, which it would refuse (and an allowlist
    Collector would drop), and which of the shape's keys the framework does not emit."""
    todas = E.claves_permitidas()
    salida = {}
    for op, g in grupos.items():
        propias = set(E.ATRIBUTOS.get(TIPO_LAB.get(op, ""), {}))
        nativas = set(g["claves"])
        salida[op] = {"emite": len(nativas), "aceptadas_por_el_esquema": sorted(nativas & propias),
                      "fuera_del_esquema": sorted(nativas - propias),
                      "fuera_de_toda_la_lista": sorted(nativas - todas),
                      "del_esquema_que_no_emite": sorted(propias - nativas) if propias else None}
    return salida


def hijo_de(span: dict, indice: dict) -> str | None:
    p = indice.get(span["parent"]) if span["parent"] else None
    return p["name"] if p else ("<fuera>" if span["parent"] else None)


def arbol_texto(spans: list[dict]) -> list[str]:
    """`depth name` lines of one trace, children after their parent, ordered by start time."""
    indice = {s["span"]: s for s in spans}
    hijos: dict[str | None, list[dict]] = {}
    for s in sorted(spans, key=lambda x: x["inicio"]):
        hijos.setdefault(s["parent"] if s["parent"] in indice else None, []).append(s)
    lineas: list[str] = []

    def bajar(s, nivel):
        lineas.append(f"{nivel} {s['name']}")
        for h in hijos.get(s["span"], []):
            bajar(h, nivel + 1)
    for r in hijos.get(None, []):
        bajar(r, 0)
    return lineas


def continuidad(strands: dict, servidor: list[dict]) -> dict:
    """Does the Strands trace continue into the server's spans (the lab's `authorize`, SDK server span, `handle_tool`, SQL)?"""
    sp = strands["spans"]
    raiz = next(s for s in sp if operacion(s) == "invoke_agent")
    T = raiz["trace"]
    propios = {s["span"]: s for s in sp}
    en_t = [s for s in servidor if s["trace"] == T]
    fuera = [s for s in servidor if s["trace"] != T]
    todos = {**propios, **{s["span"]: s for s in servidor}}
    llamadas = [s for s in servidor if s["name"] == "authorize" and s["attrs"].get("mcp.method.name") == "tools/call"]
    cliente_sdk = [s for s in sp if s["name"].startswith("MCP send")]
    return {
        "traza_del_agente": T,
        "spans_del_servidor_en_la_traza": dict(sorted(Counter(s["name"].split(" ")[0] for s in en_t).items())),
        "spans_del_servidor_en_otras_trazas": dict(sorted(Counter(s["name"].split(" ")[0] for s in fuera).items())),
        "llamadas_a_herramientas_en_el_servidor": len(llamadas),
        "de_ellas_en_la_traza_del_agente": sum(1 for s in llamadas if s["trace"] == T),
        "padre_de_authorize": sorted({hijo_de(s, todos) or "-" for s in llamadas if s["trace"] == T}),
        "spans_mcp_del_sdk_en_el_proceso_del_framework": [{"name": s["name"], "en_la_traza_del_agente": s["trace"] == T,
                                                          "padre": hijo_de(s, propios)} for s in cliente_sdk
                                                         if s["attrs"].get("mcp.method.name") == "tools/call"],
        "una_sola_traza_hasta_el_sql": any(s["name"].startswith("SELECT") and s["trace"] == T for s in servidor),
        "arbol": arbol_texto(sp + en_t),
    }


def tokens(spans: list[dict]) -> list[dict]:
    return [{k: v for k, v in sorted(s["attrs"].items()) if "usage" in k or "token" in k}
            for s in sorted(spans, key=lambda x: x["inicio"]) if operacion(s) == "chat"]


REDACCION_STRANDS = "gen_ai_unredacted_attributes="     # Strands' own switch: with an empty list every sensitive field is redacted


def raiz_trace(st: dict) -> str:
    return next(s for s in st["spans"] if operacion(s) == "invoke_agent")["trace"]


def resumen_strands(st: dict, servidor: list[dict]) -> dict:
    grupos = por_operacion(st["spans"])
    return {"versiones": st["versiones"], "parada": st["parada"], "herramientas": st["herramientas"],
            "spans": len(st["spans"]), "spans_en_la_traza_del_agente": sum(1 for s in st["spans"] if s["trace"] == raiz_trace(st)),
            "alcances": sorted({s["alcance"] for s in st["spans"]}),
            "nombres": [s["name"] for s in sorted(st["spans"], key=lambda x: x["inicio"])],
            "operaciones": grupos, "cobertura": cobertura(grupos), "tokens": tokens(st["spans"]),
            "uso_acumulado": st["uso_acumulado"], "continuidad": continuidad(st, servidor), "fugas": st["fugas"],
            "con_filas": st["con_filas"]}


def lado_servidor(servidor: list[dict]) -> dict:
    """What the server saw of a framework that sends no trace context: every request starts its own trace."""
    llamadas = [s for s in servidor if s["name"] == "authorize" and s["attrs"].get("mcp.method.name") == "tools/call"]
    return {"spans": len(servidor), "trazas": len({s["trace"] for s in servidor}),
            "llamadas_a_herramientas": len(llamadas), "trazas_de_las_llamadas": len({s["trace"] for s in llamadas}),
            "authorize_con_padre": sum(1 for s in llamadas if s["parent"]),
            "por_nombre": dict(sorted(Counter(s["name"].split(" ")[0] for s in servidor).items()))}


def langfuse(vs, T: str, esperados: int) -> dict:
    auth = vs.auth_langfuse()
    obs = vs.observaciones(T, auth, espera=150, minimo=esperados)
    blob = json.dumps(obs, ensure_ascii=False, default=str)
    gen = [o for o in obs if o.get("type") == "GENERATION"]
    return {
        "observaciones": len(obs), "esperadas": esperados,
        "tipos": dict(sorted(Counter(o.get("type") for o in obs).items())),
        "generaciones": [{"modelo": o.get("providedModelName") or o.get("model"), "usageDetails": o.get("usageDetails"),
                          "costDetails": o.get("costDetails")} for o in sorted(gen, key=lambda x: x["startTime"])],
        "con_entrada_o_salida": sum(1 for o in obs if o.get("input") or o.get("output")),
        "usuario_en_el_agente": bool(next((o for o in obs if o.get("type") == "AGENT"), {}).get("userId")),
        "canarios_en_langfuse": {k: v in blob for k, v in CANARIOS.items()},
        "mascaras": blob.count("****"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=str(S17 / "resultados" / "frameworks.json"))
    ap.add_argument("--langfuse", action="store_true", help="also read the Strands trace back from Langfuse (needs the stack)")
    a = ap.parse_args(argv)
    for v in ("st", "lg"):
        if not (VENVS / v / "bin" / "python").exists():
            print(f"[frameworks] venv `{v}` not found under VENVS_S15 / semana-15/.venvs", file=sys.stderr)
            return 2
    vs = cargar_stack() if a.langfuse else None
    if vs and vs.peticion(f"{vs.LANGFUSE}/api/public/health")[0] != 200:
        print("[frameworks] the stack is not up: run semana-17/observabilidad/arrancar.sh first", file=sys.stderr)
        return 2
    os.environ["LAB_OBS_SALT"] = secrets.token_hex(16)
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "NO_CONTENT"
    E.ESTRICTO = True
    exp = configurar_trazas(otlp_http=OTLP if a.langfuse else None)
    informe: dict = {"fecha": time.strftime("%Y-%m-%d"), "modelo_guionado": True, "modelo": MODELO}
    with tempfile.TemporaryDirectory() as t, Laboratorio(tenant="lab") as lab:
        tmp = Path(t)
        (tmp / "guion.json").write_text(json.dumps(guion()), encoding="utf-8")
        srv = lab.entorno.servidores["normal"]
        token = lab.token("analista")

        # 1. the lab's own instrumentation (activity 3), same turns, same task
        exp.clear()
        r, _, _ = lab.correr(turnos_principal(sql=SQL), tarea={**TAREA, "tarea": TEXTO_TAREA})
        estable(exp)
        spans_lab = resumen(exp.get_finished_spans())
        raiz = next(s for s in spans_lab if s["name"].startswith("invoke_agent"))
        del_agente = [s for s in spans_lab if s["trace"] == raiz["trace"]]
        informe["laboratorio"] = {
            "estado": r.estado, "spans_en_la_traza": len(del_agente),
            "operaciones": por_operacion([s for s in del_agente
                                          if s["name"].split(" ")[0] in ("invoke_agent", "chat", "execute_tool")]),
            "tokens": tokens(del_agente)}

        # 2. Strands: native OpenTelemetry, real server. First as it comes, then with its own redaction switch on
        T = {}
        for clave, extra in (("strands", None), ("strands_redactado", {"OTEL_SEMCONV_STABILITY_OPT_IN": REDACCION_STRANDS})):
            exp.clear()
            st = lanzar("st", "agente_strands.py", tmp, srv.url, token, OTLP if a.langfuse else None, extra)
            estable(exp)
            informe[clave] = resumen_strands(st, resumen(exp.get_finished_spans()))
            T[clave] = informe[clave]["continuidad"]["traza_del_agente"]
        informe["strands_redactado"]["configuracion"] = f"OTEL_SEMCONV_STABILITY_OPT_IN={REDACCION_STRANDS}"

        # 3. LangGraph: no native OpenTelemetry; the run tree it does build, and what the server saw of it
        exp.clear()
        lg = lanzar("lg", "agente_langgraph.py", tmp, srv.url, token)
        estable(exp)
        informe["langgraph"] = {k: lg[k] for k in ("versiones", "servidor_real", "motivo_sin_servidor", "spans_otel", "nombres_otel",
                                                 "atributos_gen_ai_otel", "arboles", "runs", "tipos", "usage_en_el_rastro", "fugas")}
        informe["langgraph"]["servidor"] = lado_servidor(resumen(exp.get_finished_spans()))
        tokens_probe = [token] + list(lab.entorno._tokens.values())
    cerrar_trazas()
    texto = json.dumps(informe, ensure_ascii=False)
    informe["sin_token_en_el_informe"] = not any(tk in texto for tk in tokens_probe)

    if a.langfuse:
        for clave in ("strands", "strands_redactado"):
            c = informe[clave]["continuidad"]
            esperados = informe[clave]["spans_en_la_traza_del_agente"] + sum(c["spans_del_servidor_en_la_traza"].values())
            informe[f"langfuse_{clave}"] = langfuse(vs, T[clave], esperados)
    informe["completo"] = bool(informe["strands"]["spans"] and informe["langgraph"]["runs"] and informe["sin_token_en_el_informe"]
                               and (not a.langfuse or informe["langfuse_strands"]["observaciones"] > 0))
    Path(a.salida).write_text(json.dumps(informe, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: informe[k] for k in informe if k not in ("laboratorio",)}, indent=1, ensure_ascii=False)[:9000])
    return 0 if informe["completo"] else 1


if __name__ == "__main__":
    sys.exit(main())
