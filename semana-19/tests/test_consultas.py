"""Week 19, activity 6b: the questions endpoints and the agent's worker, offline ($0, no AWS).

Owner-only reads (another subject gets the same 404 as a missing id), validation before any write, the start failure
ends as 'error', and the worker stores only the state on failure (no detail, no trace).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from consultas import api, worker  # noqa: E402


def evento(ruta: str, sub: str = "usuario-a", cuerpo: dict | None = None, id_consulta: str | None = None) -> dict:
    e = {"routeKey": ruta, "requestContext": {"authorizer": {"jwt": {"claims": {"sub": sub, "tenant": "t1", "scope": "x"}}}}}
    if cuerpo is not None:
        e["body"] = json.dumps(cuerpo)
    if id_consulta is not None:
        e["pathParameters"] = {"id": id_consulta}
    return e


class Almacen:
    def __init__(self):
        self.items: dict[str, dict] = {}
        self.invocaciones: list[dict] = []

    def guardar(self, item):
        self.items[item["id"]] = dict(item)

    def obtener(self, id_consulta):
        return self.items.get(id_consulta)

    def invocar(self, payload):
        self.invocaciones.append(payload)

    def actualizar(self, id_consulta, estado):
        self.items[id_consulta]["estado"] = estado


def _llamar(a: Almacen, e: dict, *, fallo_invocar: bool = False) -> dict:
    def invocar(payload):
        if fallo_invocar:
            raise RuntimeError("throttled")
        a.invocar(payload)
    return api.manejar(e, guardar=a.guardar, obtener=a.obtener, invocar=invocar, actualizar=a.actualizar,
                       ahora=lambda: 1000, nuevo_id=lambda: "c-1")


def test_crear_guarda_por_hash_del_sujeto_y_arranca_el_agente():
    a = Almacen()
    r = _llamar(a, evento("POST /consultas", cuerpo={"pregunta": "  ¿Stock de SKU-0001?  "}))
    assert r["statusCode"] == 202 and json.loads(r["body"]) == {"id": "c-1", "estado": "en_curso"}
    item = a.items["c-1"]
    assert item["dueno"] == api.dueno_de({"sub": "usuario-a"}) and item["dueno"] != "usuario-a"
    assert item["expira"] == 1000 + api.VIGENCIA_SEGUNDOS
    assert a.invocaciones == [{"id": "c-1", "claims": {"sub": "usuario-a", "tenant": "t1", "scope": "x"},
                               "pregunta": "¿Stock de SKU-0001?"}]


def test_pregunta_invalida_no_escribe_nada():
    for cuerpo in ({}, {"pregunta": ""}, {"pregunta": "   "}, {"pregunta": "x" * (api.MAX_PREGUNTA + 1)}, {"pregunta": 7}):
        a = Almacen()
        r = _llamar(a, evento("POST /consultas", cuerpo=cuerpo))
        assert r["statusCode"] == 400 and a.items == {} and a.invocaciones == [], cuerpo


def test_cuerpo_que_no_es_json_es_400():
    e = evento("POST /consultas")
    e["body"] = "{no json"
    a = Almacen()
    assert _llamar(a, e)["statusCode"] == 400 and a.items == {}


def test_si_no_arranca_el_agente_la_consulta_queda_en_error_sin_detalle():
    a = Almacen()
    r = _llamar(a, evento("POST /consultas", cuerpo={"pregunta": "hola"}), fallo_invocar=True)
    assert r["statusCode"] == 503 and "throttled" not in r["body"]
    assert a.items["c-1"]["estado"] == "error"


def test_solo_el_dueno_lee_su_respuesta_y_otro_recibe_404_igual_que_si_no_existiera():
    a = Almacen()
    _llamar(a, evento("POST /consultas", sub="usuario-a", cuerpo={"pregunta": "hola"}))
    a.items["c-1"].update({"estado": "completada", "respuesta": "Stock: 4", "decisiones_json": '[{"tool":"x"}]'})
    ajeno = api.manejar(evento("GET /consultas/{id}", sub="usuario-b", id_consulta="c-1"),
                        guardar=a.guardar, obtener=a.obtener, invocar=a.invocar, actualizar=a.actualizar)
    inexistente = api.manejar(evento("GET /consultas/{id}", sub="usuario-b", id_consulta="no-existe"),
                              guardar=a.guardar, obtener=a.obtener, invocar=a.invocar, actualizar=a.actualizar)
    assert ajeno["statusCode"] == 404 and ajeno == {**inexistente, "body": ajeno["body"]}
    propia = api.manejar(evento("GET /consultas/{id}", sub="usuario-a", id_consulta="c-1"),
                         guardar=a.guardar, obtener=a.obtener, invocar=a.invocar, actualizar=a.actualizar)
    cuerpo = json.loads(propia["body"])
    assert propia["statusCode"] == 200
    assert cuerpo == {"id": "c-1", "estado": "completada", "respuesta": "Stock: 4", "decisiones": [{"tool": "x"}]}
    assert "dueno" not in propia["body"] and "expira" not in propia["body"]


def test_sin_sujeto_en_el_token_no_hay_acceso():
    e = evento("GET /consultas/{id}", id_consulta="c-1")
    e["requestContext"]["authorizer"]["jwt"]["claims"] = {"tenant": "t1"}
    a = Almacen()
    assert api.manejar(e, guardar=a.guardar, obtener=a.obtener, invocar=a.invocar, actualizar=a.actualizar)["statusCode"] == 401


def test_el_trabajador_guarda_la_respuesta_del_agente():
    guardados = {}
    res = worker.procesar({"id": "c-1", "claims": {"sub": "u"}, "pregunta": "hola"},
                          correr=lambda ev: {"estado": "completada", "respuesta": "Hola", "decisiones": [{"a": 1}]},
                          actualizar=lambda i, c: guardados.update({i: c}))
    assert res == {"id": "c-1", "estado": "completada"}
    assert guardados["c-1"] == {"estado": "completada", "respuesta": "Hola", "decisiones_json": '[{"a": 1}]'}


def test_el_trabajador_ante_un_fallo_guarda_solo_el_estado_sin_detalle():
    guardados = {}

    def fallar(ev):
        raise RuntimeError("secreto: traza interna con la pregunta")

    worker.procesar({"id": "c-2", "claims": {"sub": "u"}, "pregunta": "hola"}, correr=fallar,
                    actualizar=lambda i, c: guardados.update({i: c}))
    assert guardados["c-2"] == {"estado": "error", "respuesta": "", "decisiones_json": "[]"}


def test_el_log_de_operador_no_lleva_la_pregunta_ni_el_mensaje_de_la_excepcion(caplog):
    import logging

    from consultas import worker

    secreto = "PREGUNTA-SECRETA-7731"

    def correr_que_falla(_):
        raise ValueError("mensaje con " + secreto)

    guardado = {}
    with caplog.at_level(logging.ERROR):
        worker.procesar({"id": "c1", "claims": {}, "pregunta": secreto},
                        correr=correr_que_falla, actualizar=lambda i, c: guardado.update(c))
    assert guardado["estado"] == "error"
    assert "ValueError" in caplog.text
    assert secreto not in caplog.text
