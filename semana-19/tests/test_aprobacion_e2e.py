"""Week 19, activity 8: the approval check end to end, offline (a fake AWS that behaves like the workflow)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))


def _cargar():
    spec = importlib.util.spec_from_file_location("aprobacion_e2e", S19 / "eval" / "aprobacion_e2e.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


A = _cargar()
C = A.C
TOKEN_TAREA = "AQCEAAAAKgAAAAMAAAAAAAAAAeXampleTaskToken+/=="
SUBS = {"analista": "sub-analista-1", "comprador": "sub-comprador-2", "aprobador": "sub-aprobador-3"}


class AwsFalso:
    """Two proposals; the first is approved, the second expires. Knobs break one check at a time."""

    def __init__(self, espera_s=120, propone=True, analista_http=403, aprobador_http=200, escritor_como=("order_writer",),
                 token_en_logs=0, vence_con="States.Timeout"):
        self.espera_s, self.propone, self.analista_http, self.aprobador_http = espera_s, propone, analista_http, aprobador_http
        self.escritor_como, self.n_logs, self.vence_con = escritor_como, token_en_logs, vence_con
        self.reloj, self.ejecs, self.ordenes, self.llamadas = 1000.0, [], {}, []

    # identity
    def sub(self, u):
        return SUBS[u]

    def token(self, u):
        return f"jwt-{u}"

    def cuentas(self):
        return ["123456789012"]

    # database lookups (loader, read-only)
    def skus_pendientes(self):
        return {"SKU-0011"}

    def un_cedis(self):
        return 1

    def espera_de_la_maquina_s(self):
        return self.espera_s

    def leer_ordenes(self, ids):
        por = {"APPROVED": 4, "REJECTED": 1, "PENDING_APPROVAL": 2}
        for o in self.ordenes.values():
            por[o["status"]] = por.get(o["status"], 0) + 1
        return {"ordenes": [self.ordenes[i] for i in ids if i in self.ordenes], "por_estado": por,
                "privilegios": {"order_writer": {"SELECT": True, "INSERT": True, "UPDATE": True, "DELETE": False},
                                "copilot_ro": {"SELECT": False, "INSERT": False, "UPDATE": False, "DELETE": False}}}

    # the agent, through the API
    def medir(self, tarea):
        self.reloj += 5
        herramientas = []
        if self.propone:
            n = len(self.ejecs) + 1
            sku = tarea["tarea"].split("artículo ")[1].split(" ")[0]
            self.ejecs.append({"arn": f"arn:aws:states:us-east-1:123456789012:execution:semana19-aprobacion:e{n}",
                               "nombre": f"e{n}", "inicio": self.reloj, "estado": "RUNNING"})
            self.ordenes[100 + n] = {"po_id": 100 + n, "sku": sku, "status": "PENDING_APPROVAL",
                                     "requested_by": SUBS["comprador"], "decided_by": None, "decided_level": None,
                                     "required_level": "comprador"}
            herramientas = [{"gen_ai.tool.name": "proponer_orden_compra", "lab.tool.status": "ok", "lab.step": 1}]
        return {"id_tarea": tarea["id"], "estado": "respondida", "costo_usd": 0.02, "tokens_entrada": 15000,
                "tokens_salida": 900, "latencia_s": 12.0, "pasos": 3, "herramientas": 1, "spans_herramientas": herramientas}

    def ejecuciones(self):
        return list(self.ejecs)

    def _ejec(self, arn_o_nombre):
        return next(e for e in self.ejecs if arn_o_nombre in (e["arn"], e["nombre"]))

    def estado_de(self, arn):
        return self._ejec(arn)["estado"]

    def registro_del_token(self, nombre):
        n = int(nombre[1:])
        return {"presente": True, "po_id": 100 + n, "nivel_requerido": "comprador"}

    def token_en_logs(self, nombre):
        return self.n_logs

    def http(self, metodo, ruta, token, cuerpo):
        self.llamadas.append((ruta, token))
        e = self._ejec(ruta.rsplit("/", 1)[-1])
        if token == "jwt-analista":
            return self.analista_http, {}
        if e["estado"] != "RUNNING":
            return 404, {"estado": "no_encontrada"}
        if self.aprobador_http != 200:
            return self.aprobador_http, {"estado": "misma_persona"}
        e["estado"] = "SUCCEEDED"
        orden = self.ordenes[100 + int(e["nombre"][1:])]
        orden.update(status="APPROVED", decided_by=SUBS["aprobador"], decided_level="gerente")
        return 200, {"estado": "aprobada"}

    def historial(self, arn):
        e = self._ejec(arn)
        n = int(e["nombre"][1:])
        eventos = [{"type": "TaskScheduled", "taskScheduledEventDetails": {"parameters": json.dumps(
                       {"FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:registrar",
                        "Payload": {"id": e["nombre"], "token": TOKEN_TAREA, "solicitud": {"solicitante": SUBS["comprador"]}}})}}]
        if e["estado"] == "SUCCEEDED":
            eventos += [{"type": "TaskStateEntered", "stateEnteredEventDetails": {"name": "EscribirDecision"}},
                        {"type": "TaskStateExited", "stateExitedEventDetails": {"name": "EscribirDecision", "output": json.dumps(
                            {"resultado": {"po_id": 100 + n, "estado": "APPROVED"}})}}]
        else:
            eventos += [{"type": "ExecutionTimedOut", "executionTimedOutEventDetails": {"error": self.vence_con}}]
        return eventos

    def politicas_del_escritor(self):
        return [{"Statement": [{"Effect": "Allow", "Action": "rds-db:connect",
                                "Resource": [f"arn:aws:rds-db:us-east-1:123456789012:dbuser:db-X/{u}" for u in self.escritor_como]},
                               {"Effect": "Allow", "Action": ["logs:PutLogEvents"], "Resource": "*"}]}]


def correr(aws, tope=None):
    def dormir(s):
        for e in aws.ejecs:
            if e["estado"] == "RUNNING" and e["nombre"] == "e2" and s >= aws.espera_s:
                e["estado"] = "TIMED_OUT"
    return A.flujo(aws, medir=aws.medir, tope=tope or C.Tope(usd=A.TOPE_USD, tokens=A.TOPE_TOKENS),
                   reloj=lambda: aws.reloj, dormir=dormir)


def test_las_cinco_comprobaciones_pasan_en_orden():
    r = correr(AwsFalso())
    assert [(p["paso"], p["ok"]) for p in r["pasos"]] == [(0, True), (1, True), (2, True), (3, True), (4, True), (5, True)]
    cuatro = r["pasos"][4]
    assert cuatro["escritor_se_conecta_como"] == ["order_writer"] and cuatro["paso_escribir_decision"]["estado"] == "APPROVED"
    cinco = r["pasos"][5]
    assert cinco["error"] == "States.Timeout" and cinco["orden"]["status"] == "PENDING_APPROVAL"
    assert cinco["decididas_antes"] == cinco["decididas_despues"] and cinco["aprobacion_tardia_http"] == 404
    assert r["skus"] == ["SKU-0012", "SKU-0013"]   # SKU-0011 has a pending order


def test_el_solicitante_y_el_aprobador_son_personas_distintas():
    r = correr(AwsFalso())
    assert r["pasos"][3]["aprobador_distinto_del_solicitante"] is True
    assert r["pasos"][4]["orden"]["requested_by"] == "<sub:comprador>" and r["pasos"][4]["orden"]["decided_by"] == "<sub:aprobador>"


@pytest.mark.parametrize("perilla, paso_que_falla", [
    ({"propone": False}, 0), ({"token_en_logs": 1}, 1), ({"analista_http": 200}, 2), ({"aprobador_http": 403}, 3),
    ({"escritor_como": ("order_writer", "copilot_ro")}, 4), ({"vence_con": "States.TaskFailed"}, 5),
    ({"espera_s": 86400}, 5)])
def test_una_comprobacion_que_falla_detiene_el_flujo(perilla, paso_que_falla):
    r = correr(AwsFalso(**perilla))
    assert r["pasos"][-1]["ok"] is False and r["pasos"][-1]["paso"] == paso_que_falla
    assert all(p["ok"] for p in r["pasos"][:-1])


def test_la_espera_de_24_h_no_corre_el_paso_5_y_lo_dice():
    r = correr(AwsFalso(espera_s=86400))
    assert r["pasos"][-1]["motivo"] == "espera_de_prueba_no_desplegada"


def test_el_tope_aborta_la_propuesta_y_lo_reporta():
    lim = C.limite_de_tarea()
    r = correr(AwsFalso(), tope=C.Tope(usd=lim.usd * 0.5, tokens=A.TOPE_TOKENS))
    assert r["pasos"] == [{"paso": 0, "comprobacion": "el agente propone la orden", "ok": False, "motivo": "tope_del_script"}]
    assert r["tareas"] == []


def test_el_historial_guardado_no_trae_el_token_de_tarea_ni_los_sujetos_ni_la_cuenta():
    r = correr(AwsFalso())
    texto = json.dumps(r, ensure_ascii=False)
    assert TOKEN_TAREA not in texto and "<task-token>" in texto
    assert not any(s in texto for s in SUBS.values()) and "123456789012" not in json.dumps(
        r["historial_aprobada"]) and "123456789012" not in json.dumps(r["historial_vencida"])


def test_el_paso_de_decision_se_lee_del_historial():
    h = AwsFalso()
    h.ejecs.append({"arn": "a", "nombre": "e1", "inicio": 0, "estado": "SUCCEEDED"})
    assert A.paso_decision(h.historial("a")) == {"po_id": 101, "estado": "APPROVED"}
    assert A.paso_decision([{"type": "ExecutionTimedOut"}]) is None


def test_conectar_solo_como_lee_los_usuarios_de_rds_db_connect():
    assert A.conectar_solo_como(AwsFalso().politicas_del_escritor()) == ["order_writer"]
    assert A.conectar_solo_como([{"Statement": [{"Effect": "Deny", "Action": "rds-db:connect", "Resource": "x/u"}]}]) == []


def test_la_propuesta_trae_los_datos_que_exige_la_politica():
    texto = A.texto_de_propuesta("SKU-0012", 1, "prueba")
    assert all(x in texto for x in ("SKU-0012", "CEDIS 1", A.FECHA_REQUERIDA, "motivo", str(A.CANTIDAD)))
    from consultas.api import MAX_PREGUNTA
    assert len(C.texto_de_la_tarea(A.tarea_de_propuesta("x", "SKU-0012", 1, "prueba de vencimiento"))) <= MAX_PREGUNTA


def test_elegir_skus_salta_los_pendientes_y_falla_si_no_hay():
    assert A.elegir_skus({"SKU-0011", "SKU-0013"}) == ["SKU-0012", "SKU-0014"]
    with pytest.raises(RuntimeError):
        A.elegir_skus(set(A.CANDIDATOS))


def test_topes_en_el_codigo_y_simulacion_sin_aws(monkeypatch, capsys):
    assert (A.TOPE_USD, A.TOPE_TOKENS) == (0.20, 100_000)
    import boto3
    monkeypatch.setattr(boto3, "Session", lambda *a, **k: pytest.fail("la simulación no toca AWS"))
    assert A.main([]) == 0 and "Simulación" in capsys.readouterr().out
