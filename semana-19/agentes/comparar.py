"""Week 19, activity 7: the three tools paths compared on the same 10 Spanish tasks.

  (a) directo   POST /consultas with an analista's Cognito token; the agent Lambda invokes the tools function
  (b) gateway   the same, with the agent deployed with CAMINO_HERRAMIENTAS=gateway (MCP, the user's token, Cedar)
  (c) agentes   InvokeAgent on semana19-agentes-comparacion (alias comparacion) with enableTrace

Simulation by default: it prints the plan and the caps and calls nothing. `--si` acts, one path per run (the deployed
agent decides between (a) and (b), so computo is redeployed between them); `--politica --si` is the live Policy test;
`--informe` aggregates the raw files offline. Run with the admin profile (Cognito admin auth and the direct invoke of
the tools function for the verifier need it):

    S19_PERFIL=manuel-admin .venv/bin/python semana-19/agentes/comparar.py --camino directo --si

Caps, in the code: TOPE_USD and TOPE_TOKENS over the three paths together. Before each task the run checks that
what was spent (this path and the paths already run) plus week 17's per-task limit still fits; otherwise it stops
and records why. On path (c) Bedrock Agents has no budget of its own: the script ends the stream when the trace shows
the task over that limit.

Metrics per task: success with week 13's verifier (agente/verificar.py, the agent's SQL re-run through the tools
function: week 16's guard, copilot_ro, read-only), latency, tokens, cost (construccion.PRECIOS), steps, tool calls,
guardrail and Policy blocks. Files are written with comun.redaccion: no account, no token, no home path.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

S19 = Path(__file__).resolve().parents[1]
RAIZ = S19.parent
sys.path.insert(0, str(S19))
sys.path.insert(0, str(RAIZ / "semana-17"))

from agente import construccion as K  # noqa: E402
from agente.handler import run_id_de  # noqa: E402
from comun.redaccion import redactar  # noqa: E402
from herramientas import contrato  # noqa: E402

TOPE_USD = 1.20
TOPE_TOKENS = 500_000
CAMINOS = ("directo", "gateway", "agentes")
N_TAREAS = 10
TAREAS = RAIZ / "semana-13" / "golden" / "tareas_es.jsonl"
SALIDA = S19 / "resultados" / "agentes"
REGION = "us-east-1"
ESPERA_MAX_S = 150
SONDEO_S = 1.0
TIPO_DE_HERRAMIENTA = {"directo": "function", "gateway": "extension"}


# ---------------------------------------------------------------- the tasks and the caps

def seleccionar_tareas(n: int = N_TAREAS, archivo: Path = TAREAS) -> list[dict]:
    """The first n Spanish gold tasks that expect an answer with one key, in file order: the three paths are compared
    on execution accuracy, and path (c) has no structured answer to report several keys or another state."""
    tareas = [json.loads(l) for l in archivo.read_text(encoding="utf-8").splitlines() if l.strip()]
    elegidas = [t for t in tareas if t["estado_esperado"] == "respondida" and len(t.get("salida", {})) == 1]
    if len(elegidas) < n:
        raise RuntimeError(f"solo hay {len(elegidas)} tareas elegibles")
    return elegidas[:n]


def limite_de_tarea():
    """Week 17's per-task limit, the same the agent Lambda enforces (construccion.politica_de_la_tarea)."""
    return K.politica_de_la_tarea().tarea


@dataclass
class Tope:
    usd: float = TOPE_USD
    tokens: int = TOPE_TOKENS
    gastado_usd: float = 0.0
    gastado_tokens: int = 0

    def cabe_otra(self) -> bool:
        lim = limite_de_tarea()
        return self.gastado_usd + lim.usd <= self.usd and self.gastado_tokens + lim.tokens <= self.tokens

    def sumar(self, usd: float, tokens: int) -> None:
        self.gastado_usd += usd or 0.0
        self.gastado_tokens += tokens or 0


def costo(tokens_entrada: int, tokens_salida: int) -> float:
    p = K.PRECIOS
    return round(tokens_entrada / 1e6 * p.entrada_1m + tokens_salida / 1e6 * p.salida_1m, 6)


def tope_con_lo_previo(carpeta: Path = SALIDA, excepto: str | None = None) -> Tope:
    """The global cap minus what the paths already run spent (their raw files)."""
    tope = Tope()
    for c in CAMINOS:
        archivo = carpeta / f"crudo_{c}.json"
        if c != excepto and archivo.exists():
            gasto = json.loads(archivo.read_text(encoding="utf-8"))["gasto"]
            tope.sumar(gasto["usd"], gasto["tokens"])
    return tope


# ---------------------------------------------------------------- week 13's verifier over the tools function

class _Cursor:
    def __init__(self, filas):
        self._filas = filas
        ancho = len(filas[0]) if filas else 1
        self.description = [SimpleNamespace(name=f"c{i}") for i in range(ancho)] if filas is not None else None

    def fetchall(self):
        return list(self._filas)


class ConexionPorHerramientas:
    """A psycopg-shaped connection for week 13's verifier: each SELECT runs through the tools function (week 16's
    guard, copilot_ro, a read-only transaction, at most 200 rows); the SET statements are the function's own."""

    def __init__(self, ejecutar_sql: Callable[[str], dict]):
        self._ejecutar = ejecutar_sql

    @contextlib.contextmanager
    def transaction(self):
        import psycopg
        try:
            yield self
        except psycopg.Rollback:
            pass

    def execute(self, sql: str):
        import psycopg
        if sql.lstrip().upper().startswith("SET "):
            return _Cursor(None)
        r = self._ejecutar(sql)
        if "filas" not in r:
            raise psycopg.Error(str(r.get("error") or "sin_filas"))
        if r.get("truncado"):
            raise RuntimeError("resultado truncado por la función de herramientas")
        return _Cursor([tuple(f) for f in r["filas"]])


def cargar_verificador():
    return K.cargar_de_semana13("agente/verificar.py", "verificar_semana13").verificar


def verificar(tarea: dict, estado: str, resultados: list, ejecutar_sql: Callable, verificador=None) -> dict:
    v = verificador or cargar_verificador()
    return v(tarea, {"resultados": resultados}, ConexionPorHerramientas(ejecutar_sql), estado)


# ---------------------------------------------------------------- paths (a) and (b): the questions API

def _spans_de_la_tarea(lineas: list[dict], run_id: str | None) -> dict:
    agente = [l for l in lineas if l.get("tipo") == "invoke_agent"]
    propio = [l for l in agente if l["attrs"].get("lab.run.id") == run_id]
    herramientas = [l for l in lineas if l.get("tipo") == "execute_tool"]
    return {"agente": propio[0]["attrs"] if len(propio) == 1 else None, "herramientas": [h["attrs"] for h in herramientas],
            "ajenos": len(agente) - len(propio)}


def medir_api(tarea: dict, camino: str, *, token: str, http: Callable, spans_entre: Callable, reloj=time.time,
              dormir=time.sleep) -> dict:
    """One task through POST /consultas and its polling. Tasks run one at a time, so the spans written between the
    POST and the answer are this task's; the agent span is matched by its run id too."""
    inicio = reloj()
    st, r = http("POST", "/consultas", token, {"pregunta": tarea["tarea"]})
    if st != 202:
        return {"id_tarea": tarea["id"], "camino": camino, "estado": "error_api", "http": st}
    id_consulta = r["id"]
    while True:
        st, r = http("GET", f"/consultas/{id_consulta}", token, None)
        if r.get("estado") != "en_curso" or reloj() - inicio > ESPERA_MAX_S:
            break
        dormir(SONDEO_S)
    fin = reloj()
    s = _spans_de_la_tarea(spans_entre(inicio, fin + 5), run_id_de(id_consulta))
    a = s["agente"] or {}
    herr = s["herramientas"]
    ent, sal = int(a.get("lab.run.tokens.input") or 0), int(a.get("lab.run.tokens.output") or 0)
    decisiones = r.get("decisiones") or []
    return {
        "id_tarea": tarea["id"], "camino": camino, "estado": r.get("estado", "sin_respuesta"),
        "latencia_s": round(fin - inicio, 2), "tokens_entrada": ent, "tokens_salida": sal,
        "costo_usd": a.get("lab.run.cost_usd") if a.get("lab.run.cost_usd") is not None else costo(ent, sal),
        "pasos": a.get("lab.run.steps"), "herramientas": a.get("lab.run.tool_calls"),
        "errores_herramienta": a.get("lab.run.tool_errors"), "motivo": a.get("lab.outcome.reason"),
        "tipos_de_herramienta": sorted({h.get("gen_ai.tool.type") for h in herr}),
        "bloqueos_capa": sum(1 for d in decisiones if d.get("accion") not in (None, "allow")),
        "bloqueos_guardrail": int(str(a.get("lab.outcome.reason", "")).startswith("guardrail")),
        "bloqueos_politica": sum(1 for h in herr if h.get("error.type") == "rechazada_por_el_gateway"),
        "spans_completos": s["agente"] is not None and s["ajenos"] == 0,
        "resultados": r.get("resultados") or [], "respuesta": (r.get("respuesta") or "")[:300],
    }


# ---------------------------------------------------------------- path (c): Bedrock Agents with its trace

def leer_traza(eventos, *, limite_tokens: int) -> dict:
    """InvokeAgent's stream: the answer's chunks and the trace. Ends early (and says so) when the trace shows the task
    over the per-task token limit, since Bedrock Agents has no budget of its own."""
    texto, pasos, llamadas, consultas_ok = [], 0, [], []
    ent = sal = interv = 0
    cortada = False
    pendiente = None
    for ev in eventos:
        if "chunk" in ev:
            texto.append(ev["chunk"].get("bytes", b"").decode("utf-8"))
            continue
        t = (ev.get("trace") or {}).get("trace") or {}
        orq = t.get("orchestrationTrace") or {}
        if "modelInvocationInput" in orq:
            pasos += 1
        uso = ((orq.get("modelInvocationOutput") or {}).get("metadata") or {}).get("usage") or {}
        ent, sal = ent + int(uso.get("inputTokens") or 0), sal + int(uso.get("outputTokens") or 0)
        entrada = (orq.get("invocationInput") or {}).get("actionGroupInvocationInput")
        if entrada:
            params = {p["name"]: p.get("value") for p in entrada.get("parameters") or []}
            pendiente = {"funcion": entrada.get("function"), "sql": params.get("sql")}
            llamadas.append(entrada.get("function"))
        salida = (orq.get("observation") or {}).get("actionGroupInvocationOutput")
        if salida is not None and pendiente is not None:
            try:
                cuerpo = json.loads(salida.get("text") or "{}")
            except json.JSONDecodeError:
                cuerpo = {}
            if pendiente["funcion"] == "ejecutar_sql" and "filas" in cuerpo:
                consultas_ok.append(pendiente["sql"])
            pendiente = None
        for g in ("guardrailTrace",):
            if (t.get(g) or {}).get("action") == "INTERVENED":
                interv += 1
        if ent + sal > limite_tokens:
            cortada = True
            break
    return {"texto": "".join(texto), "pasos": pasos, "llamadas": llamadas, "consultas_ok": consultas_ok,
            "tokens_entrada": ent, "tokens_salida": sal, "intervenciones": interv, "cortada": cortada}


def medir_agentes(tarea: dict, *, invocar: Callable, solicitante: str, reloj=time.time) -> dict:
    inicio = reloj()
    sesion = uuid.uuid4().hex
    r = invocar(sesion=sesion, texto=tarea["tarea"], atributos={contrato.SOLICITANTE: solicitante})
    tr = leer_traza(r, limite_tokens=limite_de_tarea().tokens)
    fin = reloj()
    (clave,) = tarea["salida"]
    # No structured answer here: the reported SQL is the last SELECT that returned rows (an adapted measurement).
    resultados = [{"clave": clave, "sql": tr["consultas_ok"][-1], "valor": tr["texto"]}] if tr["consultas_ok"] else []
    estado = "limite_alcanzado" if tr["cortada"] else ("respondida" if resultados else "sin_consulta")
    return {
        "id_tarea": tarea["id"], "camino": "agentes", "estado": estado, "latencia_s": round(fin - inicio, 2),
        "tokens_entrada": tr["tokens_entrada"], "tokens_salida": tr["tokens_salida"],
        "costo_usd": costo(tr["tokens_entrada"], tr["tokens_salida"]), "pasos": tr["pasos"],
        "herramientas": len(tr["llamadas"]), "errores_herramienta": len(tr["llamadas"]) - len(tr["consultas_ok"]),
        "motivo": "corte_por_tokens" if tr["cortada"] else None, "tipos_de_herramienta": ["action_group"],
        "bloqueos_capa": None, "bloqueos_guardrail": tr["intervenciones"], "bloqueos_politica": None,
        "spans_completos": False, "resultados": resultados, "respuesta": tr["texto"][:300],
    }


# ---------------------------------------------------------------- aggregation

def percentil(valores: list[float], p: float) -> float | None:
    """Nearest rank (no interpolation): with 10 values, p95 is the largest."""
    v = sorted(x for x in valores if x is not None)
    if not v:
        return None
    return v[max(0, math.ceil(p / 100 * len(v)) - 1)]


def resumir(filas: list[dict]) -> dict:
    hechas = [f for f in filas if f.get("estado") != "no_corrida"]
    exito = [f for f in hechas if (f.get("verificacion") or {}).get("exito")]
    suma = lambda k: sum(f.get(k) or 0 for f in hechas)  # noqa: E731
    return {
        "tareas": len(filas), "corridas": len(hechas), "exito": len(exito),
        "tasa_exito": round(len(exito) / len(hechas), 3) if hechas else None,
        "latencia_p50_s": percentil([f.get("latencia_s") for f in hechas], 50),
        "latencia_p95_s": percentil([f.get("latencia_s") for f in hechas], 95),
        "tokens": suma("tokens_entrada") + suma("tokens_salida"), "costo_usd": round(suma("costo_usd"), 6),
        "pasos_promedio": round(suma("pasos") / len(hechas), 2) if hechas else None,
        "herramientas_promedio": round(suma("herramientas") / len(hechas), 2) if hechas else None,
        "bloqueos_guardrail": suma("bloqueos_guardrail"), "bloqueos_capa": suma("bloqueos_capa"),
        "bloqueos_politica": suma("bloqueos_politica"),
    }


def correr_camino(camino: str, tareas: list[dict], *, medir: Callable, ejecutar_sql: Callable, tope: Tope,
                  verificador=None) -> dict:
    filas = []
    for t in tareas:
        if not tope.cabe_otra():
            filas.append({"id_tarea": t["id"], "camino": camino, "estado": "no_corrida", "motivo": "tope_del_script"})
            continue
        f = medir(t)
        tope.sumar(f.get("costo_usd") or 0.0, (f.get("tokens_entrada") or 0) + (f.get("tokens_salida") or 0))
        estado_verificado = "respondida" if f["estado"] == "respondida" else f["estado"]
        f["verificacion"] = verificar(t, estado_verificado, f.get("resultados") or [], ejecutar_sql, verificador)
        filas.append(f)
    hechas = [f for f in filas if f.get("estado") != "no_corrida"]
    gasto = {"usd": round(sum(f.get("costo_usd") or 0 for f in hechas), 6),
             "tokens": sum((f.get("tokens_entrada") or 0) + (f.get("tokens_salida") or 0) for f in hechas)}
    return {"camino": camino, "filas": filas, "resumen": resumir(filas), "gasto": gasto,
            "tope": {"usd": TOPE_USD, "tokens": TOPE_TOKENS}}


# ---------------------------------------------------------------- the live Policy test

PROPUESTA_DE_PRUEBA = {"sku": "SKU-0001", "cantidad": 1, "motivo": "prueba de politica", "cedis": 99999,
                       "fecha_requerida": "2026-12-05"}


def probar_politica(llamar_como: Callable[[str, str | None], dict], listar_como: Callable[[str], list[str]],
                    subs: dict[str, str]) -> list[dict]:
    """The protected tool is proponer_orden_compra (gateway/politicas/proponer.cedar): the approval is not an agent
    tool. The test proposal names a CEDIS that does not exist, so a call the Policy lets through is refused by the
    tool before any workflow starts (no pending order to clean up). `llamar_como(usuario, solicitante)` returns
    {"paso": bool, "codigo": int|None, "error_herramienta": str|None}."""
    casos = [("analista", "analista", "denegada"), ("comprador", "comprador", "permitida"),
             ("aprobador", "aprobador", "denegada"), ("comprador", "analista", "denegada")]
    filas = []
    for usuario, de_quien, esperado in casos:
        r = llamar_como(usuario, subs[de_quien])
        obtenido = "permitida" if r["paso"] else "denegada"
        filas.append({"usuario": usuario, "solicitante": "propio" if de_quien == usuario else "ajeno",
                      "esperado": esperado, "obtenido": obtenido, "ok": obtenido == esperado,
                      "codigo_jsonrpc": r.get("codigo"), "error_herramienta": r.get("error_herramienta")})
    for usuario in ("analista", "comprador", "aprobador"):
        visibles = listar_como(usuario)
        filas.append({"usuario": usuario, "lista_de_herramientas": sorted(visibles),
                      "ve_proponer": contrato.nombre_en_gateway("proponer_orden_compra") in visibles})
    return filas


# ---------------------------------------------------------------- real clients (only with --si)

USUARIOS = {"analista": ("analista-prueba", "ANALISTA_PRUEBA_PASSWORD"),
            "comprador": ("comprador-prueba", "COMPRADOR_PRUEBA_PASSWORD"),
            "aprobador": ("aprobador-prueba", "APROBADOR_PRUEBA_PASSWORD")}


class Aws:  # pragma: no cover - live only
    def __init__(self, perfil: str):
        import boto3
        self.s = boto3.Session(profile_name=perfil, region_name=REGION)
        self.cuenta = self.s.client("sts").get_caller_identity()["Account"]
        cfn = self.s.client("cloudformation")

        def salidas(pila):
            try:
                return {o["OutputKey"]: o["OutputValue"] for o in cfn.describe_stacks(StackName=pila)["Stacks"][0]["Outputs"]}
            except Exception:  # noqa: BLE001 - a stack that is not deployed has no outputs
                return {}
        self.computo, self.gateway = salidas("semana19-computo"), salidas("semana19-gateway")
        self.agentes = salidas("semana19-agentes-comparacion")
        self.herramientas = cfn.describe_stack_resource(
            StackName="semana19-computo", LogicalResourceId="FuncionHerramientas10B13045")["StackResourceDetail"]["PhysicalResourceId"]
        self.lam = self.s.client("lambda")
        conf = self.lam.get_function_configuration(FunctionName=self.computo["ArnAgente"])["Environment"]["Variables"]
        self.camino_desplegado, self.grupo_spans = conf.get("CAMINO_HERRAMIENTAS", "directo"), conf["GRUPO_SPANS"]
        secretos = Path.home() / "s19-secretos" / "usuarios-prueba.env"
        self._secretos = dict(l.split("=", 1) for l in secretos.read_text(encoding="utf-8").splitlines() if "=" in l)
        self._tokens: dict[str, str] = {}

    def token(self, clave: str) -> str:
        if clave not in self._tokens:
            usuario, var = USUARIOS[clave]
            r = self.s.client("cognito-idp").admin_initiate_auth(
                UserPoolId=self.computo["IdUsuarios"], ClientId=self.computo["IdClienteApp"],
                AuthFlow="ADMIN_USER_PASSWORD_AUTH", AuthParameters={"USERNAME": usuario, "PASSWORD": self._secretos[var]})
            self._tokens[clave] = r["AuthenticationResult"]["AccessToken"]
        return self._tokens[clave]

    def sub(self, clave: str) -> str:
        from agente.cliente_gateway import claims  # read without verifying: Cognito signed them
        return claims(self.token(clave))["sub"]

    def http(self, metodo, ruta, token, cuerpo):
        import urllib.error
        import urllib.request
        req = urllib.request.Request(self.computo["UrlApi"].rstrip("/") + ruta, method=metodo,
                                     data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                     headers={"Authorization": f"Bearer {token}", "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def spans_entre(self, desde_s: float, hasta_s: float) -> list[dict]:
        logs = self.s.client("logs")
        lineas, siguiente = [], None
        while True:
            kw = {"logGroupName": self.grupo_spans, "startTime": int(desde_s * 1000), "endTime": int(hasta_s * 1000)}
            if siguiente:
                kw["nextToken"] = siguiente
            r = logs.filter_log_events(**kw)
            lineas += [json.loads(e["message"]) for e in r.get("events", [])]
            siguiente = r.get("nextToken")
            if not siguiente:
                return lineas

    def ejecutar_sql(self, sql: str) -> dict:
        r = self.lam.invoke(FunctionName=self.herramientas, Payload=json.dumps(
            contrato.entrada_de_herramienta("ejecutar_sql", {"sql": sql}, None)).encode())
        return json.loads(r["Payload"].read())

    def invocar_agente(self, *, sesion, texto, atributos):
        r = self.s.client("bedrock-agent-runtime").invoke_agent(
            agentId=self.agentes["IdAgente"], agentAliasId=self.agentes["IdAlias"], sessionId=sesion, inputText=texto,
            enableTrace=True, sessionState={"sessionAttributes": atributos})
        return r["completion"]


def _escribir(nombre: str, datos: Any, cuentas=()) -> Path:
    SALIDA.mkdir(parents=True, exist_ok=True)
    archivo = SALIDA / nombre
    archivo.write_text(json.dumps(redactar(datos, cuentas), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
    return archivo


def plan(camino: str | None, tareas: list[dict]) -> dict:
    lim = limite_de_tarea()
    previo = tope_con_lo_previo(excepto=camino)
    return {"simulacion": True, "camino": camino, "tareas": [t["id"] for t in tareas],
            "tope": {"usd": TOPE_USD, "tokens": TOPE_TOKENS},
            "gastado_en_otros_caminos": {"usd": round(previo.gastado_usd, 6), "tokens": previo.gastado_tokens},
            "limite_por_tarea": {"usd": lim.usd, "tokens": lim.tokens},
            "peor_caso_de_este_camino": {"usd": round(lim.usd * len(tareas), 4), "tokens": lim.tokens * len(tareas)},
            "llamadas": {"directo": "POST/GET /consultas (analista) + logs:FilterLogEvents + lambda:Invoke (verificador)",
                         "gateway": "igual que directo, con el agente desplegado con CAMINO_HERRAMIENTAS=gateway",
                         "agentes": "bedrock-agent-runtime:InvokeAgent (enableTrace) + lambda:Invoke (verificador)"}}


def main(argv=None) -> int:  # pragma: no cover - the CLI around the tested functions
    import os
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--camino", choices=CAMINOS)
    ap.add_argument("--politica", action="store_true")
    ap.add_argument("--informe", action="store_true")
    ap.add_argument("--si", action="store_true", help="actuar (por omisión solo simula)")
    a = ap.parse_args(argv)
    tareas = seleccionar_tareas()
    if a.informe:
        crudos = {c: json.loads((SALIDA / f"crudo_{c}.json").read_text(encoding="utf-8"))
                  for c in CAMINOS if (SALIDA / f"crudo_{c}.json").exists()}
        print(json.dumps({c: d["resumen"] for c, d in crudos.items()}, ensure_ascii=False, indent=2))
        return 0
    if not a.si:
        print(json.dumps(plan(a.camino, tareas), ensure_ascii=False, indent=2))
        print("Simulación: no se llamó a AWS. Agrega --si para actuar.")
        return 0
    aws = Aws(os.environ.get("S19_PERFIL", "manuel-admin"))
    if a.politica:
        from agente.cliente_gateway import probar_como, listar_como
        url = aws.gateway["UrlGateway"]
        filas = probar_politica(lambda u, s: probar_como(url, aws.token(u), {**PROPUESTA_DE_PRUEBA, contrato.SOLICITANTE: s}),
                                lambda u: listar_como(url, aws.token(u)), {u: aws.sub(u) for u in USUARIOS})
        print(_escribir("politica_en_vivo.json", {"fecha": time.strftime("%Y-%m-%d"), "filas": filas}, [aws.cuenta]))
        return 0 if all(f.get("ok", True) for f in filas) else 1
    if a.camino is None:
        ap.error("--camino es obligatorio con --si")
    if a.camino != "agentes" and aws.camino_desplegado != a.camino:
        raise SystemExit(f"el agente desplegado usa {aws.camino_desplegado}; despliega computo con CAMINO_HERRAMIENTAS={a.camino}")
    if a.camino == "agentes":
        medir = lambda t: medir_agentes(t, invocar=aws.invocar_agente, solicitante=aws.sub("analista"))  # noqa: E731
    else:
        medir = lambda t: medir_api(t, a.camino, token=aws.token("analista"), http=aws.http,  # noqa: E731
                                    spans_entre=aws.spans_entre)
    datos = correr_camino(a.camino, tareas, medir=medir, ejecutar_sql=aws.ejecutar_sql,
                          tope=tope_con_lo_previo(excepto=a.camino))
    datos["fecha"] = time.strftime("%Y-%m-%d")
    print(_escribir(f"crudo_{a.camino}.json", datos, [aws.cuenta]))
    print(json.dumps(datos["resumen"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
