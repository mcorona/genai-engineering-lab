"""Tests of the Claude Agent SDK adapter (activity 10), without calling the API or the CLI."""
import asyncio
import json

import pytest

sdk = pytest.importorskip("claude_agent_sdk")
from agente_sdk.agente import PREFIJO, SISTEMA_SDK, herramientas_sdk  # noqa: E402
from herramientas import Contexto, Herramientas, definiciones  # noqa: E402

TAREA = {"id": "t-es", "tarea": "x", "estado_esperado": "respondida", "salida": {"n": {"tipo": "numero", "descripcion": "n"}}}
FINAL = {"estado": "respondida", "respuesta": "4", "resultados": [{"clave": "n", "sql": "SELECT 4", "valor": 4}],
         "evidencia": [], "supuestos": []}


def preparar(usuario="analista"):
    eventos, estado = [], {"final": None}
    tools = {t.name: t for t in herramientas_sdk(Herramientas(Contexto.de_usuario(usuario)), TAREA, eventos, estado)}
    return tools, eventos, estado


def llamar(tools, nombre, args):
    res = asyncio.run(tools[nombre].handler(args))
    return json.loads(res["content"][0]["text"]), res["is_error"]


def test_mismo_catalogo_y_esquemas():
    tools, _, _ = preparar()
    assert list(tools) == [d["name"] for d in definiciones()] + ["responder"]
    for d in definiciones():
        assert tools[d["name"]].description == d["description"] and tools[d["name"]].input_schema == d["input_schema"]
    assert PREFIJO in SISTEMA_SDK


def test_misma_respuesta_que_las_nativas():
    tools, eventos, _ = preparar("almacenista")
    nat = Herramientas(Contexto.de_usuario("almacenista"))
    for nombre, args in [("validar_sql", {"sql": "SELECT vta_art FROM vtadia"}), ("buscar_regla_negocio", {"consulta": "cobertura"}),
                         ("validar_sql", {"sql": "DELETE FROM exidet"}), ("describir_esquema", {})]:
        res, is_error = llamar(tools, nombre, args)
        assert res == json.loads(json.dumps(nat.llamar(nombre, args), default=str)) and is_error == (not res["ok"])
    assert [e["herramienta"] for e in eventos] == ["validar_sql", "buscar_regla_negocio", "validar_sql", "describir_esquema"]


def test_responder_valida_contra_la_tarea():
    tools, _, estado = preparar()
    res, err = llamar(tools, "responder", {**FINAL, "resultados": []})
    assert err and res["error"]["tipo"] == "respuesta_invalida" and estado["final"] is None
    res, err = llamar(tools, "responder", FINAL)
    assert not err and estado["final"]["resultados"][0]["valor"] == 4
