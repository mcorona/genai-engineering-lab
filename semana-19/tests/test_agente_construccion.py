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
        K._entrada_de_herramienta("borrar_todo", {})


def test_precios_de_4_5_son_los_verificados():
    deps = K.construir(cliente_converse=Converse(), cliente_lambda=Lambda(), entorno=ENTORNO, exportar=lambda _: None)
    assert deps["precios"] == Precios(entrada_1m=1.1, salida_1m=5.5)
