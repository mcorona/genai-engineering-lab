"""Week 20, activity 3: prompt caching behind `modelo.invocar`, offline ($0, no AWS, no model). ADR 0014.

The flag CACHE_PROMPT places the cache points in the Converse adapter; off is week 19's request byte for byte. The
budget, the span cost and the EMF cost count the cache tokens at their own prices."""
from __future__ import annotations

import copy
import io
import json
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente import construccion as K  # noqa: E402
from agente import converse_adaptador as A  # noqa: E402
from agente import handler as H  # noqa: E402
from agente import modelo  # noqa: E402
from agente.converse_adaptador import api_converse, peticion_a_converse, respuesta_a_anthropic  # noqa: E402
from agente.presupuesto import Precios, Presupuesto  # noqa: E402
from ia import config  # noqa: E402
from presupuestos.politica import Limite, Politica  # noqa: E402

SNAPSHOT = json.loads((S19 / "tests" / "snapshots" / "converse_semana19.json").read_text(encoding="utf-8"))
GUARD = {"guardrailIdentifier": "gid", "guardrailVersion": "3"}
MODELO_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
ENTORNO = {"MODELO": MODELO_ID, "FUNCION_HERRAMIENTAS": "fn-herramientas", "GUARDRAIL_ID": "gid-prueba",
           "GUARDRAIL_VERSION": "1", "GRUPO_SPANS": "/semana19/agente/spans"}


def _cuerpo(n_mensajes: int) -> dict:
    """A loop body with the task, then (assistant tool_use, user tool_result) pairs, n messages in all (odd)."""
    mensajes = [{"role": "user", "content": "pregunta"}]
    for i in range(1, n_mensajes // 2 + 1):
        mensajes.append({"role": "assistant", "content": [{"type": "tool_use", "id": f"tu{i}", "name": "describir_esquema",
                                                           "input": {}}]})
        mensajes.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"tu{i}", "content": "ok"}]})
    return {"model": "x", "max_tokens": 900, "system": "SISTEMA", "output_config": {"effort": "low"},
            "tools": [{"name": "describir_esquema", "description": "d", "input_schema": {"type": "object"}}],
            "messages": mensajes}


def _puntos(req: dict) -> list[tuple]:
    """Where the request carries cache points: ("system", i) or ("messages", i), with the point block."""
    lugares = [("system", i, b) for i, b in enumerate(req["system"]) if "cachePoint" in b]
    for i, m in enumerate(req["messages"]):
        lugares += [("messages", i, b) for b in m["content"] if "cachePoint" in b]
    lugares += [("tools", i, t) for i, t in enumerate(req.get("toolConfig", {}).get("tools", [])) if "cachePoint" in t]
    return lugares


# --- the flag in off is week 19 ---------------------------------------------------------------------------------

def test_en_off_la_peticion_es_la_de_la_semana_19_byte_por_byte():
    req = peticion_a_converse(SNAPSHOT["cuerpo"], modelo_id=MODELO_ID, guardrail=GUARD)
    assert json.dumps(req, sort_keys=True) == json.dumps(SNAPSHOT["peticion"], sort_keys=True)
    via_modelo = []
    modelo.invocar(lambda r: via_modelo.append(copy.deepcopy(r)) or {"output": {"message": {"content": []}}},
                   SNAPSHOT["cuerpo"], config=modelo.ConfigModelo(modelo_id=MODELO_ID, guardrail=GUARD))
    assert json.dumps(via_modelo[0], sort_keys=True) == json.dumps(SNAPSHOT["peticion"], sort_keys=True)
    assert "cachePoint" not in json.dumps(via_modelo[0])


def test_el_valor_por_omision_es_off_en_la_configuracion_y_en_su_copia():
    assert config.CACHE_PROMPT == K.CACHE_PROMPT_POR_OMISION == "off"
    assert config.CACHE_TTL == K.CACHE_TTL_POR_OMISION == "5m"
    assert tuple(config.MODOS_CACHE) == K.MODOS_CACHE == A.MODOS_CACHE
    assert tuple(config.TTLS_CACHE) == K.TTLS_CACHE == A.TTLS_CACHE
    assert K.cache({}) == ("off", "5m")


# --- where the points go ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("n", [1, 3, 5, 7, 15, 25])
def test_historial_pone_el_punto_al_final_y_en_el_del_paso_anterior_nunca_en_la_primera_llamada(n):
    req = peticion_a_converse(_cuerpo(n), modelo_id=MODELO_ID, guardrail=GUARD, cache="historial")
    esperadas = [i for i in (n - 3, n - 1) if i >= 2]
    assert [(lugar, i) for lugar, i, _ in _puntos(req)] == [("messages", i) for i in esperadas]
    for i in esperadas:   # the point is the last block of its message, after a model turn
        assert "cachePoint" in req["messages"][i]["content"][-1]
        assert any("toolUse" in b for m in req["messages"][:i] for b in m["content"])
    assert len(_puntos(req)) <= A.MAX_PUNTOS_CACHE


def test_sistema_pone_un_punto_tras_el_prompt_y_cubre_las_herramientas():
    req = peticion_a_converse(_cuerpo(5), modelo_id=MODELO_ID, guardrail=GUARD, cache="sistema")
    assert [(lugar, i) for lugar, i, _ in _puntos(req)] == [("system", 1)]
    assert req["system"][0] == {"text": "SISTEMA"}


@pytest.mark.parametrize("modo", A.MODOS_CACHE)
@pytest.mark.parametrize("n", [1, 3, 9, 31])
def test_nunca_mas_de_4_puntos(modo, n):
    assert len(_puntos(peticion_a_converse(_cuerpo(n), modelo_id=MODELO_ID, cache=modo))) <= A.MAX_PUNTOS_CACHE


@pytest.mark.parametrize("ttl, bloque", [("5m", {"cachePoint": {"type": "default"}}),
                                        ("1h", {"cachePoint": {"type": "default", "ttl": "1h"}})])
def test_el_ttl_es_el_de_la_configuracion(ttl, bloque):
    req = peticion_a_converse(_cuerpo(5), modelo_id=MODELO_ID, cache="historial+sistema", ttl=ttl)
    assert [b for _, _, b in _puntos(req)] == [bloque] * 3


def test_valores_desconocidos_fallan_cerrado():
    with pytest.raises(ValueError):
        modelo.ConfigModelo(modelo_id=MODELO_ID, cache="todo")
    with pytest.raises(ValueError):
        modelo.ConfigModelo(modelo_id=MODELO_ID, ttl="24h")
    with pytest.raises(RuntimeError, match="CACHE_PROMPT desconocido"):
        K.cache({K.CACHE_PROMPT: "todo"})
    with pytest.raises(RuntimeError, match="CACHE_TTL desconocido"):
        K.cache({K.CACHE_TTL: "2h"})


@pytest.mark.parametrize("modo", A.MODOS_CACHE)
def test_guardrail_modelo_y_prompt_no_cambian_con_ningun_valor(modo):
    base = peticion_a_converse(_cuerpo(7), modelo_id=MODELO_ID, guardrail=GUARD)
    req = peticion_a_converse(_cuerpo(7), modelo_id=MODELO_ID, guardrail=GUARD, cache=modo)
    assert req["guardrailConfig"] == base["guardrailConfig"] == GUARD
    assert req["modelId"] == MODELO_ID and req["inferenceConfig"] == base["inferenceConfig"]
    assert req["toolConfig"] == base["toolConfig"]
    assert [b for b in req["system"] if "text" in b] == base["system"]
    sin_puntos = [{"role": m["role"], "content": [b for b in m["content"] if "cachePoint" not in b]}
                  for m in req["messages"]]
    assert sin_puntos == base["messages"]


def test_los_puntos_no_tocan_el_historial_del_bucle():
    cuerpo = _cuerpo(7)
    antes = copy.deepcopy(cuerpo)
    peticion_a_converse(cuerpo, modelo_id=MODELO_ID, cache="historial+sistema")
    assert cuerpo == antes


# --- the deployed path: construction, two users, cost ---------------------------------------------------------

class ConverseConCache:
    """Model stand-in for 3 calls: two reads, then the answer. From the second call on it reports cache tokens."""

    USO = [{"inputTokens": 3000, "outputTokens": 100},
           {"inputTokens": 50, "outputTokens": 120, "cacheReadInputTokens": 0, "cacheWriteInputTokens": 4500},
           {"inputTokens": 40, "outputTokens": 200, "cacheReadInputTokens": 4500, "cacheWriteInputTokens": 600}]

    def __init__(self):
        self.pedidos = []

    def converse(self, **req):
        self.pedidos.append(copy.deepcopy(req))
        n = len(self.pedidos)
        if n < 3:
            bloque = {"toolUse": {"toolUseId": f"tooluse_{id(self)}_{n}", "name": "ejecutar_sql",
                                  "input": {"sql": "SELECT COUNT(*) FROM legado.prvmst"}}}
        else:
            bloque = {"toolUse": {"toolUseId": f"tooluse_{id(self)}_{n}", "name": "responder", "input": {
                "estado": "respondida", "respuesta": "Hay 12 proveedores", "resultados": [], "evidencia": [],
                "supuestos": [], "pregunta_aclaracion": None}}}
        return {"output": {"message": {"role": "assistant", "content": [bloque]}}, "stopReason": "tool_use",
                "usage": self.USO[n - 1]}


class Lambda:
    def invoke(self, FunctionName, Payload):
        return {"Payload": io.BytesIO(json.dumps({"filas": [[12]], "truncado": False, "limite": 200}).encode())}


def _correr(claims: dict, pregunta: str, modo: str = "historial"):
    converse, lineas = ConverseConCache(), []
    deps = K.construir(cliente_converse=converse, cliente_lambda=Lambda(),
                       entorno={**ENTORNO, K.CACHE_PROMPT: modo}, exportar=lineas.append)
    res = H.tratar_pregunta(pregunta, H.alcance_desde_claims(claims), **deps)
    return res, converse.pedidos, lineas


USUARIO_A = {"sub": "sub-aaaa-1111", "tenant": "tenant-norte", "scope": "legado/leer legado/proveedores"}
USUARIO_B = {"sub": "sub-bbbb-2222", "tenant": "tenant-sur", "scope": "legado/leer legado/proveedores"}


def test_seguridad_el_prefijo_fijo_es_igual_para_dos_usuarios_y_lo_demas_es_de_la_tarea():
    """The boundary of ADR 0014: tools and system are the same for every user, with nothing of the user in them; the
    first call (system, tools and the question) carries no point; every cached prefix holds this query's toolUseIds."""
    _, pa, _ = _correr(USUARIO_A, "¿Cuántos proveedores hay?")
    _, pb, _ = _correr(USUARIO_B, "¿Cuántos proveedores críticos hay en el norte?")
    assert len(pa) == len(pb) == 3
    for a, b in zip(pa, pb):
        assert a["toolConfig"] == b["toolConfig"] and a["system"] == b["system"]
        fijo = json.dumps([a["toolConfig"], a["system"]], ensure_ascii=False)
        for dato in ("sub-aaaa-1111", "tenant-norte", "sub-bbbb-2222", "tenant-sur", "proveedores hay"):
            assert dato not in fijo
    assert not _puntos(pa[0]) and not _puntos(pb[0])
    for pedidos in (pa, pb):
        for req in pedidos[1:]:
            for _, i, _ in _puntos(req):
                ids = [b["toolUse"]["toolUseId"] for m in req["messages"][:i + 1] for b in m["content"] if "toolUse" in b]
                assert ids, "a cached prefix without a model turn could be shared between users"
    ids_a = {b["toolUse"]["toolUseId"] for r in pa for m in r["messages"] for b in m["content"] if "toolUse" in b}
    ids_b = {b["toolUse"]["toolUseId"] for r in pb for m in r["messages"] for b in m["content"] if "toolUse" in b}
    assert ids_a.isdisjoint(ids_b)


def test_en_el_camino_desplegado_el_flag_llega_a_la_peticion():
    _, apagado, _ = _correr(USUARIO_A, "¿Cuántos proveedores hay?", modo="off")
    _, encendido, _ = _correr(USUARIO_A, "¿Cuántos proveedores hay?", modo="historial")
    assert all(not _puntos(r) for r in apagado)
    assert [len(_puntos(r)) for r in encendido] == [0, 1, 2]


def test_costo_del_span_y_emf_suman_la_cache_con_sus_precios():
    res, _, lineas = _correr(USUARIO_A, "¿Cuántos proveedores hay?")
    assert res.estado == "respondida"
    linea = json.loads(lineas[-1])
    attrs = linea["attrs"]
    entrada, salida = 3000 + 50 + 40, 100 + 120 + 200
    lectura, escritura = 4500, 4500 + 600
    esperado = entrada * 1.1 / 1e6 + salida * 5.5 / 1e6 + lectura * 0.11 / 1e6 + escritura * 1.375 / 1e6
    assert attrs["lab.run.tokens.input"] == entrada and attrs["lab.run.tokens.output"] == salida
    assert attrs["lab.run.tokens.cache_read"] == lectura and attrs["lab.run.tokens.cache_creation"] == escritura
    assert attrs["lab.run.cost_usd"] == pytest.approx(esperado, rel=1e-9)
    assert linea["CostoUSD"] == pytest.approx(esperado, rel=1e-9)
    assert linea["TokensCacheLectura"] == lectura and linea["TokensCacheEscritura"] == escritura


def test_sin_cache_el_costo_del_span_es_el_del_bucle():
    assert H._costo(type("R", (), {"costo_usd": 0.0123})(), Presupuesto(Politica(tarea=Limite(1, 10)), "m",
                                                                       Precios(1.1, 5.5))) == 0.0123
    assert H._costo(None, None) is None


def test_los_tokens_de_cache_salen_de_la_respuesta_de_converse():
    uso = respuesta_a_anthropic({"output": {"message": {"content": []}}, "stopReason": "end_turn",
                                 "usage": {"inputTokens": 7, "outputTokens": 3, "cacheReadInputTokens": 5000,
                                           "cacheWriteInputTokens": 800}})["usage"]
    assert uso == {"input_tokens": 7, "output_tokens": 3, "cache_read_input_tokens": 5000,
                   "cache_creation_input_tokens": 800}


def test_precios_de_cache_por_ttl():
    assert K.precios("5m") == Precios(1.1, 5.5, 0.11, 1.375)
    assert K.precios("1h") == Precios(1.1, 5.5, 0.11, 2.2)
    assert K.construir(cliente_converse=ConverseConCache(), cliente_lambda=Lambda(),
                       entorno={**ENTORNO, K.CACHE_TTL: "1h"}, exportar=lambda _: None)["precios"].cache_escritura_1m == 2.2


# --- the week 17 budget counts the cache by its dollar weight ------------------------------------------------------

def test_presupuesto_cuenta_la_cache_por_su_peso_en_dolares_caso_a_mano():
    """One call: 40 input, 200 output, 10,000 read, 4,000 written (5-minute TTL).
    USD = 40x1.1 + 200x5.5 + 10,000x0.11 + 4,000x1.375 per 1M = 0.000044 + 0.0011 + 0.0011 + 0.0055 = 0.007744.
    Tokens = 40 + 200 + 10,000x0.1 + 4,000x1.25 = 240 + 1,000 + 5,000 = 6,240 (not 14,240)."""
    p = Presupuesto(Politica(tarea=Limite(usd=1.0, tokens=1_000_000)), "claude-haiku-4-5-20251001", K.precios("5m"))
    api = p.envolver(lambda c: {"content": [], "stop_reason": "end_turn", "usage": {
        "input_tokens": 40, "output_tokens": 200, "cache_read_input_tokens": 10_000, "cache_creation_input_tokens": 4_000}})
    api({"messages": [], "max_tokens": 100})
    assert p.gastado.usd == pytest.approx(0.007744, abs=1e-12)
    assert p.gastado.tokens == 6_240
    assert p.costo_cache == pytest.approx(0.0066, abs=1e-12)
    assert (p.cache_lectura, p.cache_escritura) == (10_000, 4_000)


def test_la_estimacion_de_la_siguiente_llamada_descuenta_el_prefijo_cacheado():
    precios = K.precios("5m")
    assert precios.estimar_entrada(9_000, 0) == 9_000            # no cache: week 19's estimate
    assert precios.estimar_entrada(9_000, 6_000) == 3_000 + 600  # 6,000 expected read at 0.1
    assert precios.estimar_entrada(5_000, 6_000) == 500          # never more than the whole estimate


def test_una_tarea_con_cache_no_se_corta_antes_que_sin_cache():
    """The same 6 calls under a token cap: priced as full input they pass the cap; by dollar weight they do not."""
    usos = [{"input_tokens": 3000, "output_tokens": 150}] + [
        {"input_tokens": 40, "output_tokens": 150, "cache_read_input_tokens": 4000 + 1500 * k,
         "cache_creation_input_tokens": 1500} for k in range(5)]
    completo = sum(u["input_tokens"] + u["output_tokens"] + u.get("cache_read_input_tokens", 0)
                   + u.get("cache_creation_input_tokens", 0) for u in usos)
    tope = 30_000
    assert completo > tope
    p = Presupuesto(Politica(tarea=Limite(usd=1.0, tokens=tope)), "claude-haiku-4-5-20251001", K.precios("5m"))
    cola = iter(usos)
    api = p.envolver(lambda c: {"content": [], "stop_reason": "end_turn", "usage": next(cola)})
    for _ in usos:
        api({"messages": [], "max_tokens": 100})
    assert p.motivo is None and p.llamadas == 6 and p.gastado.tokens < tope


def test_la_semana_19_sin_cache_cuenta_igual_que_antes():
    p = Presupuesto(Politica(tarea=Limite(usd=1.0, tokens=1_000_000)), "claude-haiku-4-5-20251001", Precios(1.1, 5.5))
    api_converse  # the week 19 adapter stays importable
    p.envolver(lambda c: {"content": [], "stop_reason": "end_turn",
                          "usage": {"input_tokens": 1000, "output_tokens": 100}})({"messages": [], "max_tokens": 10})
    assert p.gastado.tokens == 1100 and p.gastado.usd == pytest.approx(1000 * 1.1 / 1e6 + 100 * 5.5 / 1e6)


# --- per step: chat spans and durations, read back by the run -------------------------------------------------

def test_un_span_chat_por_llamada_con_su_cache_y_su_costo():
    _, _, lineas = _correr(USUARIO_A, "¿Cuántos proveedores hay?")
    chat = [json.loads(l) for l in lineas if json.loads(l)["tipo"] == "chat"]
    assert [c["omitidos"] for c in chat] == [[], [], []]
    a = [c["attrs"] for c in chat]
    assert [x["lab.step"] for x in a] == [1, 2, 3]
    assert [x["gen_ai.usage.cache_read.input_tokens"] for x in a] == [0, 0, 4500]
    assert [x["gen_ai.usage.cache_creation.input_tokens"] for x in a] == [0, 4500, 600]
    agente = json.loads(lineas[-1])
    assert sum(x["lab.cost.usd"] for x in a) == pytest.approx(agente["attrs"]["lab.run.cost_usd"], rel=1e-9)
    assert len(agente["duracion_pasos_ms"]) == 3 and all(ms >= 0 for ms in agente["duracion_pasos_ms"])


def test_la_corrida_lee_los_spans_chat_y_las_duraciones():
    from agentes import comparar
    _, _, lineas = _correr(USUARIO_A, "¿Cuántos proveedores hay?")
    leidas = [json.loads(l) for l in lineas]
    run_id = leidas[-1]["attrs"]["lab.run.id"]
    s = comparar._spans_de_la_tarea(leidas, run_id)
    assert len(s["modelo"]) == 3 and s["duracion_pasos_ms"] == leidas[-1]["duracion_pasos_ms"]
