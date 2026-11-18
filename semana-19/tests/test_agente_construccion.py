"""Week 19, activity 6: the agent bound to the real parts, offline ($0): week 13 loop, Converse and tools Lambda are fakes."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente import construccion as K  # noqa: E402
from agente import handler as H  # noqa: E402
from agente.presupuesto import Precios  # noqa: E402
from herramientas import contrato  # noqa: E402

ENTORNO = {"FUNCION_HERRAMIENTAS": "fn-herramientas", "GUARDRAIL_ID": "gid-prueba", "GUARDRAIL_VERSION": "1",
            "GRUPO_SPANS": "/semana19/agente/spans"}
CLAIMS = {"sub": "usuario-prueba-1", "tenant": "lab",
          "scope": "legado/leer legado/proveedores legado/ventas legado/compras_proponer"}
PREGUNTA = "¿Cuántos proveedores hay?"


class Converse:
    """Model stand-in: first asks for a read-only query, then answers with the figure it got back."""

    def __init__(self):
        self.pedidos = []
        self.turno = 0

    def converse(self, **req):
        self.pedidos.append(req)
        self.turno += 1
        if self.turno == 1:
            bloque = {"toolUse": {"toolUseId": "t1", "name": "ejecutar_sql",
                                  "input": {"sql": "SELECT COUNT(*) FROM legado.prvmst"}}}
            parada = "tool_use"
        else:
            bloque = {"toolUse": {"toolUseId": "t2", "name": "responder", "input": {
                "estado": "respondida", "respuesta": "Hay 12 proveedores", "resultados": [], "evidencia": [],
                "supuestos": [], "pregunta_aclaracion": None}}}
            parada = "tool_use"
        return {"output": {"message": {"role": "assistant", "content": [bloque]}}, "stopReason": parada,
                "usage": {"inputTokens": 100, "outputTokens": 20}}


class Lambda:
    def __init__(self):
        self.cargas = []

    def invoke(self, FunctionName, Payload):
        self.cargas.append((FunctionName, json.loads(Payload)))
        return {"Payload": io.BytesIO(json.dumps({"filas": [[12]], "truncado": False, "limite": 200}).encode())}


def test_exigir_entorno_falla_con_la_lista_de_lo_que_falta():
    with pytest.raises(RuntimeError, match="GUARDRAIL_ID"):
        K.exigir_entorno({"FUNCION_HERRAMIENTAS": "x", "GUARDRAIL_VERSION": "1"})


def test_el_bucle_de_semana_13_se_carga_y_los_paquetes_propios_sobreviven():
    Agente, modulo = K.cargar_bucle_semana13()
    assert hasattr(Agente, "resolver")
    import agente.handler as propio  # the lab's own package is back after the isolation
    import herramientas.handler as herramientas_propias
    assert propio.tratar_pregunta and herramientas_propias.handler


def test_extremo_a_extremo_con_modelo_falso_responde_con_cifra_de_la_consulta():
    modelo, lam = Converse(), Lambda()
    deps = K.construir(cliente_converse=modelo, cliente_lambda=lam, entorno=ENTORNO, exportar=lambda _: None)
    alcance = H.alcance_desde_claims(CLAIMS)
    res = H.tratar_pregunta(PREGUNTA, alcance, **deps)
    assert res.estado == "respondida" and res.respuesta == "Hay 12 proveedores"
    assert lam.cargas == [("fn-herramientas", {"herramienta": "ejecutar_sql", "sql": "SELECT COUNT(*) FROM legado.prvmst"})]
    pedido = modelo.pedidos[0]
    assert pedido["guardrailConfig"] == {"guardrailIdentifier": "gid-prueba", "guardrailVersion": "1"}
    assert pedido["modelId"].startswith("us.anthropic.claude-haiku-4-5")


def test_presupuesto_de_la_tarea_usa_el_tope_calibrado_convertido_a_precio_de_4_5():
    pol = K.politica_de_la_tarea()
    assert pol.tarea.tokens == 46000
    assert pol.tarea.usd == pytest.approx(0.0063 * 11, rel=1e-6)


def test_herramienta_sin_binding_no_se_llama():
    with pytest.raises(ValueError):
        contrato.entrada_de_herramienta("borrar_todo", {})


def test_precios_de_4_5_son_los_verificados():
    deps = K.construir(cliente_converse=Converse(), cliente_lambda=Lambda(), entorno=ENTORNO, exportar=lambda _: None)
    assert deps["precios"] == Precios(entrada_1m=1.1, salida_1m=5.5)


def test_si_la_funcion_de_herramientas_falla_el_modelo_recibe_un_error_cerrado():
    # A failed invoke (ImportModuleError, timeout) carries the runtime's message and trace: it never reaches the model.
    class LambdaQueFalla:
        def invoke(self, FunctionName, Payload):
            cuerpo = {"errorMessage": "Unable to import module 'x': /var/task/secreto.py", "errorType": "Runtime.ImportModuleError",
                      "stackTrace": ["File /var/task/app/x.py"]}
            return {"FunctionError": "Unhandled", "Payload": io.BytesIO(json.dumps(cuerpo).encode())}

    llamar = K.llamador_de_herramientas(LambdaQueFalla(), "fn-herramientas")
    salida = llamar("describir_esquema", {})
    assert salida["ok"] is False and salida["error"]["tipo"] == "herramienta_no_disponible"
    assert "/var/task" not in json.dumps(salida) and "Unable to import" not in json.dumps(salida)


def test_el_resultado_de_la_funcion_de_herramientas_llega_al_bucle_con_ok():
    # Live: every good result lacked `ok`, so week 13 marked it is_error and counted it toward MAX_ERRORES_SEGUIDOS.
    class LambdaFija:
        def __init__(self, cuerpo):
            self.cuerpo = cuerpo

        def invoke(self, FunctionName, Payload):
            return {"Payload": io.BytesIO(json.dumps(self.cuerpo).encode())}

    bien = K.llamador_de_herramientas(LambdaFija({"filas": [[12]], "truncado": False}), "fn")("ejecutar_sql", {"sql": "SELECT 1"})
    assert bien == {"ok": True, "filas": [[12]], "truncado": False}
    mal = K.llamador_de_herramientas(LambdaFija({"error": "write_blocked", "mensaje": "Only SELECT"}), "fn")(
        "ejecutar_sql", {"sql": "DELETE FROM x"})
    assert mal == {"ok": False, "error": {"tipo": "write_blocked", "mensaje": "Only SELECT"}}


def test_extremo_a_extremo_la_consulta_correcta_no_cuenta_como_error_de_herramienta():
    deps = K.construir(cliente_converse=Converse(), cliente_lambda=Lambda(), entorno=ENTORNO, exportar=lambda _: None)
    alcance = H.alcance_desde_claims(CLAIMS)
    res = H.tratar_pregunta(PREGUNTA, alcance, **deps)
    herramienta, span = res.spans   # activity 7: one execute_tool span per call, then invoke_agent
    assert span["attrs"]["lab.run.tool_errors"] == 0 and span["attrs"]["lab.run.tool_calls"] == 1
    assert herramienta["tipo"] == "execute_tool" and herramienta["attrs"]["lab.tool.status"] == "ok"


class SumideroFalso:
    """Stands in for SumideroCloudWatch: lines are kept until vaciar(), as the real one batches them."""

    def __init__(self, falla: bool = False):
        self.pendientes, self.enviadas, self.falla = [], [], falla

    def __call__(self, linea: str) -> None:
        self.pendientes.append(linea)

    def vaciar(self) -> int:
        if self.falla:
            raise RuntimeError("AccessDenied")
        self.enviadas += self.pendientes
        self.pendientes = []
        return len(self.enviadas)


def test_el_handler_envia_los_spans_pendientes_antes_de_terminar():
    # Live, the spans group stayed empty: the sink batches and nothing called vaciar() before the invocation ended.
    sumidero = SumideroFalso()
    deps = K.construir(cliente_converse=Converse(), cliente_lambda=Lambda(), entorno=ENTORNO, exportar=sumidero)
    res = H.handler({"claims": CLAIMS, "pregunta": PREGUNTA}, None, deps=deps)
    assert res["estado"] == "respondida"
    assert sumidero.pendientes == [] and len(sumidero.enviadas) == 2
    assert [json.loads(l)["span"] for l in sumidero.enviadas] == ["execute_tool ejecutar_sql", "invoke_agent legadobridge"]


def test_si_los_spans_no_se_pueden_enviar_la_respuesta_no_cambia():
    deps = K.construir(cliente_converse=Converse(), cliente_lambda=Lambda(), entorno=ENTORNO,
                       exportar=SumideroFalso(falla=True))
    res = H.handler({"claims": CLAIMS, "pregunta": PREGUNTA}, None, deps=deps)
    assert res["estado"] == "respondida" and res["respuesta"] == "Hay 12 proveedores"


def test_la_propuesta_viaja_con_el_solicitante_fuera_de_los_argumentos_del_modelo():
    class LambdaEco:
        def invoke(self, FunctionName, Payload):
            self.carga = json.loads(Payload)
            return {"Payload": io.BytesIO(json.dumps({"solicitud_id": "sol-1"}).encode())}

    lam = LambdaEco()
    args = {"sku": "SKU-0009", "cantidad": 3, "motivo": "m", "cedis": 2, "fecha_requerida": "2026-12-05"}
    res = K.llamador_de_herramientas(lam, "fn")("proponer_orden_compra", args, solicitante="sub-1")
    assert res == {"ok": True, "solicitud_id": "sol-1"}
    assert lam.carga == {"herramienta": "proponer_orden_compra", "entrada": args, "solicitante": "sub-1"}


def test_el_agente_desplegado_ve_el_contrato_de_la_propuesta_de_la_semana_19():
    deps = K.construir(cliente_converse=Converse(), cliente_lambda=Lambda(), entorno=ENTORNO, exportar=lambda _: None)
    (prop,) = [d for d in deps["definiciones"] if d["name"] == "proponer_orden_compra"]
    assert "cedis" in prop["input_schema"]["required"] and "fecha_requerida" in prop["input_schema"]["required"]


def test_la_respuesta_lleva_sus_resultados_y_los_spans_el_id_de_la_consulta():
    """Activity 7: week 13's verifier needs the answer's keys (clave, sql, valor), and a question's spans are found by
    its id: lab.run.id is the first 12 hex digits of the question's UUID."""
    capturados = []
    id_consulta = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
    clave = {"clave": "proveedores", "sql": "SELECT COUNT(*) FROM legado.prvmst", "valor": 12}

    class ConverseConClave(Converse):
        def converse(self, **req):
            r = super().converse(**req)
            bloque = r["output"]["message"]["content"][0]["toolUse"]
            if bloque["name"] == "responder":
                bloque["input"]["resultados"] = [clave]
            return r

    deps = K.construir(cliente_converse=ConverseConClave(), cliente_lambda=Lambda(), entorno=ENTORNO,
                       exportar=capturados.append)
    res = H.handler({"id": id_consulta, "claims": CLAIMS, "pregunta": PREGUNTA}, None, deps=deps)
    assert res["estado"] == "respondida" and res["resultados"] == [clave]
    assert {json.loads(l)["attrs"]["lab.run.id"] for l in capturados if '"invoke_agent' in l} == {"0f1e2d3c4b5a"}


def test_run_id_de_solo_acepta_un_id_con_12_digitos_hex():
    assert H.run_id_de("0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0") == "0f1e2d3c4b5a"
    assert H.run_id_de("c-1") is None and H.run_id_de(None) is None
