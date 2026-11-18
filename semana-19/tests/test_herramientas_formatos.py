"""Week 19, activity 7: one adapter per event format of the tools Lambda, and the gateway's schemas (offline, $0).

- The gateway's event (arguments + tool name in the client context) and Bedrock Agents' action-group event become the
  SAME internal call the agent Lambda sends with lambda.invoke (captured from agente/construccion.py).
- gateway/herramientas.json is the projection of the loop's definitions: same tools, same fields and types, only the
  keys a gateway target accepts; the one declared difference is `solicitante` in the proposal.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente import capa_determinista as C  # noqa: E402
from agente import construccion as K  # noqa: E402
from gateway import esquemas as E  # noqa: E402
from herramientas import adaptadores as A  # noqa: E402
from herramientas import contrato  # noqa: E402
from herramientas import handler as H  # noqa: E402

PROPUESTA = {"sku": "SKU-0009", "cantidad": 40, "motivo": "reorden automático", "cedis": 1,
             "fecha_requerida": "2026-12-05"}
LLAMADAS = [("describir_esquema", {}, None),
            ("ejecutar_sql", {"sql": "SELECT art_cd FROM legado.artmst"}, None),
            ("proponer_orden_compra", PROPUESTA, "sub-comprador")]


def ctx_gateway(nombre: str):
    """The Lambda context the gateway sends: the tool's name, prefixed with the target, in client_context.custom."""
    return SimpleNamespace(client_context=SimpleNamespace(custom={
        "bedrockAgentCoreToolName": nombre, "bedrockAgentCoreMessageVersion": "1.0",
        "bedrockAgentCoreGatewayId": "semana19-gateway-x", "bedrockAgentCoreTargetId": "T1"}))


def lo_que_envia_lambda_invoke(nombre, args, solicitante):
    """The payload the agent Lambda's direct path sends (agente/construccion.llamador_de_herramientas)."""
    enviado = {}

    class Lambda:
        def invoke(self, FunctionName, Payload):
            enviado.update(json.loads(Payload))
            return {"Payload": io.BytesIO(b'{"filas": []}')}

    K.llamador_de_herramientas(Lambda(), "f")(nombre, args, solicitante)
    return enviado


def evento_gateway(args, solicitante):
    return {**args, **({"solicitante": solicitante} if solicitante else {})}


# ---------------------------------------------------------------- gateway format

@pytest.mark.parametrize("nombre,args,solicitante", LLAMADAS)
def test_evento_del_gateway_es_la_misma_llamada_que_lambda_invoke(nombre, args, solicitante):
    interno = A.desde_gateway(evento_gateway(args, solicitante), ctx_gateway(contrato.nombre_en_gateway(nombre)))
    assert interno == lo_que_envia_lambda_invoke(nombre, args, solicitante)


def test_formato_se_reconoce_por_el_contexto_y_por_la_forma():
    assert A.formato({"herramienta": "ejecutar_sql", "sql": "x"}, None) == "directo"
    assert A.formato({"sql": "x"}, ctx_gateway("herramientas___ejecutar_sql")) == "gateway"
    assert A.formato({"messageVersion": "1.0", "actionGroup": "g", "function": "ejecutar_sql"}, None) == "agentes"


@pytest.mark.parametrize("nombre", ["otro___ejecutar_sql", "herramientas___borrar_todo", "ejecutar_sql"])
def test_gateway_con_otro_target_o_herramienta_desconocida_no_llega_a_la_base(nombre):
    llamadas = []
    res = H.handler({"sql": "SELECT 1"}, ctx_gateway(nombre), conectar=lambda: llamadas.append(1))
    assert res == {"error": "entrada_invalida", "mensaje": "llamada mal formada"} and llamadas == []


def test_gateway_ejecuta_la_misma_herramienta_con_la_guardia_de_siempre():
    """The guard runs before any connection on the gateway path too."""
    llamadas = []
    res = H.handler({"sql": "DELETE FROM legado.prvmst"}, ctx_gateway("herramientas___ejecutar_sql"),
                    conectar=lambda: llamadas.append(1))
    assert res["error"] == "write_blocked" and llamadas == []


def test_gateway_el_solicitante_sale_de_los_argumentos_de_la_propuesta():
    interno = A.desde_gateway(evento_gateway(PROPUESTA, "sub-1"), ctx_gateway("herramientas___proponer_orden_compra"))
    assert interno["solicitante"] == "sub-1" and "solicitante" not in interno["entrada"]


def test_gateway_propuesta_sin_solicitante_se_rechaza_sin_iniciar():
    iniciadas = []
    res = H.handler(dict(PROPUESTA), ctx_gateway("herramientas___proponer_orden_compra"),
                    iniciar=lambda e: iniciadas.append(e) or "id")
    assert res["error"] == "sin_solicitante" and iniciadas == []


# ---------------------------------------------------------------- Bedrock Agents format

def evento_agentes(nombre, args, solicitante=None):
    tipos = {int: "integer", float: "number", bool: "boolean", str: "string"}
    return {"messageVersion": "1.0", "agent": {"name": "a", "id": "A", "alias": "L", "version": "1"},
            "actionGroup": "herramientas", "function": nombre, "inputText": "x", "sessionId": "s",
            "parameters": [{"name": k, "type": tipos[type(v)], "value": str(v)} for k, v in args.items()],
            "sessionAttributes": {"solicitante": solicitante} if solicitante else {}, "promptSessionAttributes": {}}


@pytest.mark.parametrize("nombre,args,solicitante", LLAMADAS)
def test_evento_de_bedrock_agents_es_la_misma_llamada_que_lambda_invoke(nombre, args, solicitante):
    assert A.desde_agentes(evento_agentes(nombre, args, solicitante)) == lo_que_envia_lambda_invoke(nombre, args, solicitante)


def test_bedrock_agents_recibe_la_respuesta_en_su_formato():
    ev = evento_agentes("ejecutar_sql", {"sql": "DELETE FROM legado.prvmst"})
    res = H.handler(ev, None, conectar=lambda: pytest.fail("no debe conectar"))
    assert res["messageVersion"] == "1.0"
    r = res["response"]
    assert r["actionGroup"] == "herramientas" and r["function"] == "ejecutar_sql"
    assert "responseState" not in r["functionResponse"]   # a tool error is a normal body: the model may correct itself
    assert json.loads(r["functionResponse"]["responseBody"]["TEXT"]["body"])["error"] == "write_blocked"


def test_bedrock_agents_herramienta_desconocida_se_rechaza_en_su_formato():
    res = H.handler(evento_agentes("borrar_todo", {}), None)
    cuerpo = json.loads(res["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])
    assert cuerpo == {"error": "entrada_invalida", "mensaje": "llamada mal formada"}


def test_bedrock_agents_convierte_los_tipos_de_sus_parametros():
    interno = A.desde_agentes(evento_agentes("proponer_orden_compra", PROPUESTA, "s"))
    assert interno["entrada"]["cantidad"] == 40 and interno["entrada"]["cedis"] == 1


@pytest.mark.parametrize("valor", ['["prvmst", "artmst"]', "[prvmst, artmst]", "['prvmst','artmst']"])
def test_bedrock_agents_arreglo_como_texto_llega_como_lista(valor):
    ev = evento_agentes("describir_esquema", {})
    ev["parameters"] = [{"name": "tablas", "type": "array", "value": valor}]
    assert A.desde_agentes(ev) == lo_que_envia_lambda_invoke("describir_esquema", {"tablas": ["prvmst", "artmst"]}, None)


@pytest.mark.parametrize("valor", ["prvmst", '{"a": 1}', "[1, 2]"])
def test_bedrock_agents_arreglo_mal_formado_se_rechaza_sin_conectar(valor):
    ev = evento_agentes("describir_esquema", {})
    ev["parameters"] = [{"name": "tablas", "type": "array", "value": valor}]
    res = H.handler(ev, None, conectar=lambda: pytest.fail("no debe conectar"))
    cuerpo = json.loads(res["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])
    assert cuerpo == {"error": "entrada_invalida", "mensaje": "llamada mal formada"}


# ---------------------------------------------------------------- the gateway's schemas: one source

def test_el_json_del_gateway_es_la_proyeccion_del_bucle():
    """If this fails, run `python -m gateway.esquemas` from semana-19/ and review the diff."""
    assert E.leer() == E.desde_el_bucle()


def _claves(esquema, ruta="$"):
    for k, v in esquema.items():
        yield ruta, k
        if k == "properties":
            for n, p in v.items():
                yield from _claves(p, f"{ruta}.{n}")
        elif k == "items":
            yield from _claves(v, f"{ruta}[]")


def test_el_gateway_solo_recibe_las_claves_que_admite():
    for d in E.leer():
        assert set(d) == {"name", "description", "inputSchema"}
        malas = [(r, k) for r, k in _claves(d["inputSchema"]) if k not in E.CLAVES]
        assert malas == [], d["name"]


def _tipo(prop):
    if "type" in prop:
        return prop["type"]
    (rama,) = [r for r in prop["anyOf"] if r.get("type") != "null"]
    return rama["type"]


def test_mismas_herramientas_campos_tipos_y_obligatorios_que_el_bucle():
    bucle = {d["name"]: d for d in C.definiciones_semana19()}
    gateway = {d["name"]: d for d in E.leer()}
    assert list(gateway) == list(bucle) == list(contrato.HERRAMIENTAS)
    for nombre, d in bucle.items():
        g, b = gateway[nombre]["inputSchema"], d["input_schema"]
        extra = {"solicitante"} if nombre == "proponer_orden_compra" else set()
        assert set(g["properties"]) == set(b["properties"]) | extra
        assert {n: _tipo(p) for n, p in b["properties"].items()} == \
               {n: p["type"] for n, p in g["properties"].items() if n not in extra}
        assert set(g.get("required", [])) == set(b.get("required", [])) | extra
        assert gateway[nombre]["description"] == d["description"]


def test_anyof_sin_una_rama_unica_no_tiene_proyeccion():
    with pytest.raises(ValueError):
        E.proyectar({"anyOf": [{"type": "string"}, {"type": "integer"}]})
