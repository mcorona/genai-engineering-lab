"""Week 19, activity 8: the approval workflow end to end, through the public API.

The `comprador` asks the agent for a purchase order (POST /consultas). The agent calls proponer_orden_compra, and the
tools function starts the state machine semana19-aprobacion. Then, in order:

1. the state machine waits: DescribeExecution is RUNNING. The task token is in the DynamoDB table, and no log group
   of the workflow carries it (FilterLogEvents for a prefix of it; the token is never printed or stored);
2. the `analista` calls POST /aprobaciones/{id} and gets 403 at the gateway (no `legacybridge/aprobaciones` scope);
3. the `aprobador` (group aprobadores-gerente) approves. The requester is not the approver: separation of duties, #244;
4. the row is written by order_writer. Evidence:
   - the loader's read-only lookup (`leer_ordenes`): the order is APPROVED, decided by the approver and requested by
     the buyer, and only order_writer may write the table;
   - the execution history: EscribirDecision succeeded;
   - the writer function's role may connect to the database only as order_writer (rds-db:connect);
5. a second request, with the short test wait deployed (S19_ESPERA_APROBACION_S), expires. The execution ends in
   States.Timeout, the order stays PENDING_APPROVAL with no decision, the APPROVED and REJECTED counts do not change,
   and an approval sent after the expiry is refused.

The execution histories are saved as evidence, redacted (task token, subjects, account). Simulation by default; `--si`
acts. Run with the admin profile, by Manuel:

    S19_PERFIL=manuel-admin .venv/bin/python semana-19/eval/aprobacion_e2e.py --si

Hard caps in the code over the two agent tasks: TOPE_USD and TOPE_TOKENS. A task that does not fit is not sent and the
check is reported as aborted.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

S19 = Path(__file__).resolve().parents[1]
if str(S19) not in sys.path:
    sys.path.insert(0, str(S19))

from agentes import comparar as C  # noqa: E402
from comun.redaccion import redactar  # noqa: E402


def _eval_aws():
    spec = importlib.util.spec_from_file_location("eval_aws_para_aprobacion", S19 / "eval" / "eval_aws.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


TOPE_USD = 0.20
TOPE_TOKENS = 100_000
ESPERA_MAXIMA_DE_PRUEBA_S = 600       # the expiry part needs the short wait deployed; 24 h would never end here
CANTIDAD = 5
FECHA_REQUERIDA = "2026-12-15"
SALIDA = S19 / "resultados" / "eval_aws"
ARCHIVO = "aprobacion_e2e.json"
ESTADOS_DECIDIDOS = ("APPROVED", "REJECTED")
CANDIDATOS = tuple(f"SKU-{n:04d}" for n in range(11, 61))


# ---------------------------------------------------------------- the proposal

def elegir_skus(pendientes: set[str], n: int = 2, candidatos=CANDIDATOS) -> list[str]:
    """SKUs with no pending order: the database allows one pending order per SKU (po_one_pending_per_sku), and an
    expired request leaves its order pending."""
    libres = [s for s in candidatos if s not in pendientes]
    if len(libres) < n:
        raise RuntimeError("no hay SKU sin orden pendiente entre los candidatos")
    return libres[:n]


def texto_de_propuesta(sku: str, cedis: int, motivo: str) -> str:
    return (f"Propón una orden de compra de {CANTIDAD} unidades del artículo {sku} para el CEDIS {cedis}, "
            f"con fecha requerida {FECHA_REQUERIDA} y motivo: {motivo}. No hagas otra cosa.")


def tarea_de_propuesta(id_: str, sku: str, cedis: int, motivo: str) -> dict:
    """In the shape comparar.medir_api sends: no output keys, so the message is the text itself."""
    return {"id": id_, "tarea": texto_de_propuesta(sku, cedis, motivo), "estado_esperado": "respondida", "salida": {}}


def propuso(fila: dict) -> bool:
    return any(h.get("gen_ai.tool.name") == "proponer_orden_compra" and h.get("lab.tool.status") == "ok"
               for h in fila.get("spans_herramientas") or [])


def ejecucion_nueva(ejecuciones: list[dict], desde_s: float) -> dict | None:
    """The execution the task started: the newest one that started inside the task's window."""
    nuevas = [e for e in ejecuciones if e["inicio"] >= desde_s - 1]
    return max(nuevas, key=lambda e: e["inicio"]) if nuevas else None


# ---------------------------------------------------------------- evidence, redacted

def _sin_token(valor: Any) -> Any:
    """Every `token` field becomes <task-token>, also inside the JSON text Step Functions keeps in the events (the task
    token is in RegistrarToken's TaskScheduled parameters)."""
    if isinstance(valor, dict):
        return {k: ("<task-token>" if k == "token" and v else _sin_token(v)) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_sin_token(v) for v in valor]
    if isinstance(valor, str) and valor[:1] in "{[":
        try:
            return json.dumps(_sin_token(json.loads(valor)), ensure_ascii=False, sort_keys=True)
        except ValueError:
            return valor
    return valor


def redactar_historial(eventos: list[dict], *, token: str | None, subs: dict[str, str], cuentas=()) -> list[dict]:
    """The execution history with the task token and the users' subjects replaced, then the common redaction
    (account, home, JWT, email)."""
    texto = json.dumps(_sin_token(eventos), default=str, ensure_ascii=False)
    if token:
        texto = texto.replace(token, "<task-token>")
    for etiqueta, sub in subs.items():
        if sub:
            texto = texto.replace(sub, f"<sub:{etiqueta}>")
    return redactar(json.loads(texto), cuentas)


def etiquetar(valor: Any, subs: dict[str, str]) -> Any:
    texto = json.dumps(valor, default=str, ensure_ascii=False)
    for etiqueta, sub in subs.items():
        if sub:
            texto = texto.replace(sub, f"<sub:{etiqueta}>")
    return json.loads(texto)


def paso_decision(historial: list[dict]) -> dict | None:
    """The EscribirDecision state's result in the history: the writer's {"po_id", "estado"}."""
    dentro = False
    for e in historial:
        if e.get("type") == "TaskStateEntered" and (e.get("stateEnteredEventDetails") or {}).get("name") == "EscribirDecision":
            dentro = True
        if dentro and e.get("type") == "TaskStateExited":
            salida = (e.get("stateExitedEventDetails") or {}).get("output")
            return (json.loads(salida) if isinstance(salida, str) else salida or {}).get("resultado")
    return None


def conectar_solo_como(politicas: list[dict]) -> list[str]:
    """The database users a role may connect as: the dbuser part of each rds-db:connect resource it is allowed."""
    usuarios = set()
    for p in politicas:
        for d in p.get("Statement", []):
            acciones = d.get("Action", [])
            acciones = [acciones] if isinstance(acciones, str) else acciones
            if d.get("Effect") == "Allow" and "rds-db:connect" in acciones:
                recursos = d.get("Resource", [])
                for r in [recursos] if isinstance(recursos, str) else recursos:
                    usuarios.add(str(r).rsplit("/", 1)[-1])
    return sorted(usuarios)


# ---------------------------------------------------------------- the checks, in order

def comprobar(pasos: list[dict], numero: int, nombre: str, ok: bool, **evidencia) -> bool:
    pasos.append({"paso": numero, "comprobacion": nombre, "ok": bool(ok), **evidencia})
    return bool(ok)


def flujo(aws, *, medir: Callable, tope: C.Tope, reloj=time.time, dormir=time.sleep) -> dict:
    """The five checks against injected clients (the live ones are in AwsAprobacion). Stops at the first failure: the
    next check would test a state that did not happen."""
    pasos: list[dict] = []
    pendientes = set(aws.skus_pendientes())
    sku_ok, sku_vence = elegir_skus(pendientes)
    cedis = aws.un_cedis()
    espera_s = aws.espera_de_la_maquina_s()
    subs = {u: aws.sub(u) for u in ("analista", "comprador", "aprobador")}
    tareas = []

    def proponer(id_, sku, motivo):
        if not tope.cabe_otra():
            return None
        t0 = reloj()
        f = medir(tarea_de_propuesta(id_, sku, cedis, motivo))
        tope.sumar(f.get("costo_usd") or 0.0, (f.get("tokens_entrada") or 0) + (f.get("tokens_salida") or 0))
        tareas.append({k: f.get(k) for k in ("id_tarea", "estado", "latencia_s", "tokens_entrada", "tokens_salida",
                                             "costo_usd", "pasos", "herramientas")})
        return f, ejecucion_nueva(aws.ejecuciones(), t0)

    resultado = {"pasos": pasos, "tareas": tareas, "espera_de_prueba_s": espera_s, "skus": [sku_ok, sku_vence]}
    # 1. the state machine waits, with the token in DynamoDB and not in the logs
    p = proponer("aprobacion-e2e-1", sku_ok, "prueba de aprobación de punta a punta")
    if p is None:
        comprobar(pasos, 0, "el agente propone la orden", False, motivo="tope_del_script")
        return resultado
    fila, ejec = p
    if not comprobar(pasos, 0, "el agente propuso la orden", propuso(fila) and ejec is not None,
                     estado_de_la_tarea=fila.get("estado")):
        return resultado
    for _ in range(30):
        estado = aws.estado_de(ejec["arn"])
        registro = aws.registro_del_token(ejec["nombre"])
        if estado == "RUNNING" and registro.get("presente"):
            break
        dormir(2)
    en_logs = aws.token_en_logs(ejec["nombre"]) if registro.get("presente") else None
    if not comprobar(pasos, 1, "la máquina espera con el token en DynamoDB y no en logs",
                     estado == "RUNNING" and registro.get("presente") and en_logs == 0,
                     estado_de_la_ejecucion=estado, token_en_dynamodb=bool(registro.get("presente")),
                     apariciones_del_token_en_logs=en_logs, po_id=registro.get("po_id"),
                     nivel_requerido=registro.get("nivel_requerido")):
        return resultado
    po_ok = int(registro["po_id"])
    # 2. the analyst gets 403 at the gateway
    st, _ = aws.http("POST", f"/aprobaciones/{ejec['nombre']}", aws.token("analista"), {"decision": "aprobar"})
    if not comprobar(pasos, 2, "el analista recibe 403 en el gateway", st == 403, http=st,
                     estado_despues=aws.estado_de(ejec["arn"])):
        return resultado
    # 3. the approver approves (not the requester)
    st, cuerpo = aws.http("POST", f"/aprobaciones/{ejec['nombre']}", aws.token("aprobador"), {"decision": "aprobar"})
    for _ in range(30):
        final = aws.estado_de(ejec["arn"])
        if final != "RUNNING":
            break
        dormir(2)
    if not comprobar(pasos, 3, "el aprobador aprueba", st == 200 and cuerpo.get("estado") == "aprobada" and final == "SUCCEEDED",
                     http=st, respuesta=cuerpo.get("estado"), estado_de_la_ejecucion=final,
                     aprobador_distinto_del_solicitante=subs["aprobador"] != subs["comprador"]):
        return resultado
    # 4. the row is written by order_writer
    lectura = aws.leer_ordenes([po_ok])
    (orden,) = lectura["ordenes"] or [{}]
    historial = aws.historial(ejec["arn"])
    decision = paso_decision(historial)
    usuarios = conectar_solo_como(aws.politicas_del_escritor())
    resultado["historial_aprobada"] = redactar_historial(historial, token=None, subs=subs, cuentas=aws.cuentas())
    resultado["lectura_aprobada"] = etiquetar(lectura, subs)
    if not comprobar(pasos, 4, "la fila la escribió order_writer",
                     orden.get("status") == "APPROVED" and orden.get("decided_by") == subs["aprobador"]
                     and orden.get("requested_by") == subs["comprador"]
                     and (decision or {}).get("estado") == "APPROVED" and usuarios == ["order_writer"]
                     and lectura["privilegios"]["order_writer"]["UPDATE"]
                     and not any(lectura["privilegios"]["copilot_ro"][x] for x in ("INSERT", "UPDATE", "DELETE")),
                     orden=etiquetar(orden, subs), paso_escribir_decision=decision, escritor_se_conecta_como=usuarios,
                     privilegios=lectura["privilegios"]):
        return resultado
    # 5. an expired request writes nothing
    if espera_s > ESPERA_MAXIMA_DE_PRUEBA_S:
        comprobar(pasos, 5, "una solicitud vencida no escribe", False, motivo="espera_de_prueba_no_desplegada",
                  espera_s=espera_s)
        return resultado
    antes = aws.leer_ordenes([po_ok])["por_estado"]
    p = proponer("aprobacion-e2e-2", sku_vence, "prueba de vencimiento")
    if p is None:
        comprobar(pasos, 5, "una solicitud vencida no escribe", False, motivo="tope_del_script")
        return resultado
    fila, ejec2 = p
    if not (propuso(fila) and ejec2):
        comprobar(pasos, 5, "una solicitud vencida no escribe", False, motivo="el agente no propuso",
                  estado_de_la_tarea=fila.get("estado"))
        return resultado
    registro2 = {}
    for _ in range(30):
        registro2 = aws.registro_del_token(ejec2["nombre"])
        if registro2.get("presente"):
            break
        dormir(2)
    dormir(espera_s + 10)
    for _ in range(30):
        final2 = aws.estado_de(ejec2["arn"])
        if final2 != "RUNNING":
            break
        dormir(5)
    tarde, cuerpo_tarde = aws.http("POST", f"/aprobaciones/{ejec2['nombre']}", aws.token("aprobador"), {"decision": "aprobar"})
    lectura2 = aws.leer_ordenes([int(registro2["po_id"])]) if registro2.get("po_id") else {"ordenes": [], "por_estado": {}}
    (orden2,) = lectura2["ordenes"] or [{}]
    historial2 = aws.historial(ejec2["arn"])
    error = next(((e.get("executionTimedOutEventDetails") or e.get("executionFailedEventDetails") or {}).get("error")
                  for e in historial2 if e.get("type") in ("ExecutionTimedOut", "ExecutionFailed")), None)
    sin_cambio = {k: antes.get(k, 0) for k in ESTADOS_DECIDIDOS} == {k: lectura2["por_estado"].get(k, 0) for k in ESTADOS_DECIDIDOS}
    resultado["historial_vencida"] = redactar_historial(historial2, token=None, subs=subs, cuentas=aws.cuentas())
    comprobar(pasos, 5, "una solicitud vencida no escribe",
              final2 in ("FAILED", "TIMED_OUT") and error == "States.Timeout" and orden2.get("status") == "PENDING_APPROVAL"
              and orden2.get("decided_by") is None and sin_cambio and tarde == 404,
              estado_de_la_ejecucion=final2, error=error, orden=etiquetar(orden2, subs),
              decididas_antes={k: antes.get(k, 0) for k in ESTADOS_DECIDIDOS},
              decididas_despues={k: lectura2["por_estado"].get(k, 0) for k in ESTADOS_DECIDIDOS},
              aprobacion_tardia_http=tarde, aprobacion_tardia=cuerpo_tarde.get("estado"))
    return resultado


# ---------------------------------------------------------------- real clients (only with --si)

class AwsAprobacion:  # pragma: no cover - live only
    def __init__(self, perfil: str):
        self.e = _eval_aws().AwsEval(perfil)
        self.s, self.lam = self.e.s, self.e.lam
        self.sfn = self.s.client("stepfunctions")
        cfn = self.s.client("cloudformation")
        recursos = cfn.describe_stack_resources(StackName="semana19-computo")["StackResources"]

        def fisico(tipo, prefijo):
            (r,) = [x["PhysicalResourceId"] for x in recursos if x["ResourceType"] == tipo and x["LogicalResourceId"].startswith(prefijo)]
            return r
        self.maquina = self.e.computo["ArnAprobacion"]
        self.tabla_tokens = fisico("AWS::DynamoDB::Table", "Tokens")
        self.escritor = fisico("AWS::Lambda::Function", "FuncionEscritor")
        self.grupos = sorted({x["PhysicalResourceId"] for x in recursos if x["ResourceType"] == "AWS::Logs::LogGroup"})

    def cuentas(self):
        return [self.e.cuenta]

    def token(self, u):
        return self.e.token(u)

    def sub(self, u):
        return self.e.sub(u)

    def http(self, *a):
        return self.e.http(*a)

    def _consulta(self, sql):
        return self.e.cargador_invoca({"modo": "esperados", "consultas": {"q": sql}})["esperados"]["q"]

    def skus_pendientes(self):
        return {f[0] for f in self._consulta("SELECT sku FROM purchase_orders WHERE status = 'PENDING_APPROVAL'")}

    def un_cedis(self):
        return int(self._consulta("SELECT warehouse_id FROM warehouses ORDER BY warehouse_id LIMIT 1")[0][0])

    def espera_de_la_maquina_s(self):
        d = json.loads(self.sfn.describe_state_machine(stateMachineArn=self.maquina)["definition"])
        return int(d["States"]["RegistrarToken"]["TimeoutSeconds"])

    def ejecuciones(self):
        r = self.sfn.list_executions(stateMachineArn=self.maquina, maxResults=20)["executions"]
        return [{"arn": e["executionArn"], "nombre": e["name"], "inicio": e["startDate"].timestamp(), "estado": e["status"]} for e in r]

    def estado_de(self, arn):
        return self.sfn.describe_execution(executionArn=arn)["status"]

    def registro_del_token(self, id_):
        """Presence only: the token's value is used to search the logs and is dropped; never printed or stored."""
        d = self.s.client("dynamodb").get_item(TableName=self.tabla_tokens, Key={"id": {"S": id_}}, ConsistentRead=True).get("Item")
        if not d:
            return {"presente": False}
        self._token_de = {id_: d["token"]["S"]}
        return {"presente": "token" in d, "po_id": int(d["po_id"]["N"]), "nivel_requerido": d["nivel_requerido"]["S"]}

    def token_en_logs(self, id_):
        trozo = self._token_de[id_][:48]
        logs, n = self.s.client("logs"), 0
        desde = int((time.time() - 3600) * 1000)
        for g in self.grupos:
            r = logs.filter_log_events(logGroupName=g, startTime=desde, filterPattern=json.dumps(trozo))
            n += len(r.get("events", []))
        self._token_de.pop(id_, None)
        return n

    def historial(self, arn):
        eventos, siguiente = [], None
        while True:
            kw = {"executionArn": arn, "maxResults": 200}
            if siguiente:
                kw["nextToken"] = siguiente
            r = self.sfn.get_execution_history(**kw)
            eventos += r["events"]
            siguiente = r.get("nextToken")
            if not siguiente:
                return json.loads(json.dumps(eventos, default=str))

    def leer_ordenes(self, ids):
        return self.e.cargador_invoca({"modo": "leer_ordenes", "po_ids": ids})

    def politicas_del_escritor(self):
        iam = self.s.client("iam")
        rol = self.lam.get_function_configuration(FunctionName=self.escritor)["Role"].rsplit("/", 1)[-1]
        docs = []
        for nombre in iam.list_role_policies(RoleName=rol)["PolicyNames"]:
            docs.append(iam.get_role_policy(RoleName=rol, PolicyName=nombre)["PolicyDocument"])
        return docs


def plan() -> dict:
    lim = C.limite_de_tarea()
    return {"simulacion": True, "tope": {"usd": TOPE_USD, "tokens": TOPE_TOKENS},
            "limite_por_tarea": {"usd": lim.usd, "tokens": lim.tokens}, "tareas_del_agente": 2,
            "necesita": "computo desplegado con S19_ESPERA_APROBACION_S de 60 a 600 s para el paso 5",
            "comprobaciones": ["espera con el token en DynamoDB y no en logs", "analista 403", "aprobador aprueba",
                               "la fila la escribe order_writer", "una solicitud vencida no escribe"]}


def main(argv=None) -> int:  # pragma: no cover - the CLI around the tested functions
    import os
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--si", action="store_true", help="actuar (por omisión solo simula)")
    a = ap.parse_args(argv)
    if not a.si:
        print(json.dumps(plan(), ensure_ascii=False, indent=2))
        print("Simulación: no se llamó a AWS. Agrega --si para actuar.")
        return 0
    aws = AwsAprobacion(os.environ.get("S19_PERFIL", "manuel-admin"))
    tope = C.Tope(usd=TOPE_USD, tokens=TOPE_TOKENS)
    medir = lambda t: C.medir_api(t, "directo", token=aws.token("comprador"), http=aws.http,  # noqa: E731
                                  spans_entre=aws.e.spans_entre)
    resultado = flujo(aws, medir=medir, tope=tope)
    resultado.update({"fecha": time.strftime("%Y-%m-%d"), "tope": {"usd": TOPE_USD, "tokens": TOPE_TOKENS},
                      "gasto": {"usd": round(tope.gastado_usd, 6), "tokens": tope.gastado_tokens}})
    SALIDA.mkdir(parents=True, exist_ok=True)
    archivo = SALIDA / ARCHIVO
    archivo.write_text(json.dumps(redactar(resultado, aws.cuentas()), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
    print(archivo)
    for p in resultado["pasos"]:
        print(f"{p['paso']} {'OK ' if p['ok'] else 'FALLA'} {p['comprobacion']}")
    return 0 if [p["paso"] for p in resultado["pasos"]] == [0, 1, 2, 3, 4, 5] and all(p["ok"] for p in resultado["pasos"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
