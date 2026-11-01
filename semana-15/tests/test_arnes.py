"""Actividad 2: arnés común. Contrato del Resultado, normalización de uso y costo, trazas, modelo simulado, verificador
sobre salidas guionadas y el puente entre procesos. Sin API ($0)."""
import dataclasses
import hashlib
import json
import math
import subprocess
import urllib.request

import pytest
from conftest import S13, S15, VENVS, tarea

from arnes import contrato
from arnes.adaptador import AdaptadorPropio, Registro
from arnes.simulado import DobleAnthropic, Guion, Turno, guion_respuesta, herramienta, texto
from arnes.trazas import Trazador, validar_evento

H55 = "claude-haiku-5-5"
SQL_V01 = ("SELECT COUNT(*) AS numero FROM artmst a JOIN prvmst p ON p.prv_id = a.art_prv "
           "WHERE a.art_lin = 'Tornilleria' AND p.prv_pais = 'US'")


# ---------- contrato ----------

def test_resultado_es_el_de_la_semana_13():
    import agente.loop as l13
    assert contrato.semana13().Resultado is l13.Resultado
    assert [f.name for f in dataclasses.fields(contrato.Resultado())] == [
        "estado", "final", "pasos", "herramientas", "tokens_in", "tokens_out", "costo_usd", "segundos", "motivo",
        "corrida", "errores_herramienta", "turnos_paralelos"]
    r = contrato.Resultado(estado="abstenida", pasos=2)
    assert contrato.resultado_de_dict(json.loads(json.dumps(contrato.resultado_a_dict(r)))) == r


def test_prompt_mensaje_y_respuesta_son_los_de_la_semana_13():
    import agente.loop as l13
    t = tarea("v01-es")
    assert Registro.sistema() is l13.SISTEMA
    assert Registro("x", H55, t).mensaje() == l13.mensaje_tarea(t)
    assert Registro.herramienta_responder() == l13.herramienta_responder()


@pytest.mark.parametrize("uso,esperado", [
    ({"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500}, (1200, 300)),           # Anthropic, LangChain
    ({"inputTokens": 1200, "outputTokens": 300, "totalTokens": 1500}, (1200, 300)),              # Strands
    ({"prompt_tokens": 1200, "completion_tokens": 300, "total_tokens": 1500}, (1200, 300)),      # LiteLLM
    ({"prompt_token_count": 1200, "candidates_token_count": 300}, (1200, 300)),                  # ADK
    (type("U", (), {"input_tokens": 7, "output_tokens": 3})(), (7, 3)),                          # objeto (OpenAI Agents)
    ({"input_tokens": 5}, (5, 0)),
    (None, (0, 0)),
])
def test_normalizar_uso(uso, esperado):
    assert contrato.normalizar_uso(uso) == esperado


def test_normalizar_uso_rechaza_valores_invalidos():
    with pytest.raises(ValueError):
        contrato.normalizar_uso({"input_tokens": -1})
    with pytest.raises(ValueError):
        contrato.normalizar_uso({"input_tokens": "1200"})


def test_costo_igual_al_de_litellm_en_la_sonda():
    """El precio de la semana 13 coincide con el que LiteLLM reportó en la actividad 1 para 1200/300 tokens."""
    assert math.isclose(contrato.costo(H55, 1200, 300), 0.00027)
    sonda = json.loads((S15 / "resultados" / "sonda_anthropic.json").read_text())
    for fw in ("openai_agents", "google_adk"):
        assert math.isclose(sonda["frameworks"][fw]["costo_usd"], contrato.costo(H55, 1200, 300))


def test_registro_acumula_tokens_y_costo_por_paso():
    reg = Registro("x", H55, tarea("n01-es"))
    usos = [{"input_tokens": 1000, "output_tokens": 50}, {"inputTokens": 2000, "outputTokens": 70},
            {"prompt_token_count": 3000, "candidates_token_count": 90}]
    for u in usos:
        reg.modelo(u, 5, ["ejecutar_sql"])
    reg.responder({"estado": "abstenida", "respuesta": "No hay datos de margen.", "resultados": []})
    r = reg.parar()
    assert (r.pasos, r.tokens_in, r.tokens_out) == (3, 6000, 210)
    assert math.isclose(r.costo_usd, contrato.costo(H55, 6000, 210))
    pasos = [e for e in reg.traza.eventos if e["tipo"] == "modelo"]
    assert math.isclose(sum(e["costo_usd"] for e in pasos), r.costo_usd, rel_tol=1e-6)
    assert contrato.validar_resultado(r, tarea("n01-es")) == []


def test_validar_resultado_detecta_violaciones():
    t = tarea("n01-es")
    ok = contrato.Resultado(estado="abstenida", pasos=1, tokens_in=10, tokens_out=2, costo_usd=contrato.costo(H55, 10, 2),
                            final={"estado": "abstenida", "respuesta": "x", "resultados": []})
    assert contrato.validar_resultado(ok, t) == []
    malos = {
        "costo": dataclasses.replace(ok, costo_usd=0.5),
        "sin final": dataclasses.replace(ok, final=None),
        "estado distinto": dataclasses.replace(ok, estado="respondida"),
        "límite con final": dataclasses.replace(ok, estado="limite_alcanzado"),
        "estado desconocido": dataclasses.replace(ok, estado="ok"),
        "pasos negativos": dataclasses.replace(ok, pasos=-1),
        "sin pasos": dataclasses.replace(ok, pasos=0),
    }
    for nombre, r in malos.items():
        assert contrato.validar_resultado(r, t), nombre


def test_responder_valida_como_la_semana_13():
    reg = Registro("x", H55, tarea("v01-es"))
    mala = reg.responder({"estado": "respondida", "respuesta": "7", "resultados": []})        # falta la clave n
    assert mala["ok"] is False and mala["error"]["tipo"] == "respuesta_invalida" and reg.final is None
    mala2 = reg.responder({"estado": "respondida", "respuesta": "7", "extra": 1})               # campo no permitido
    assert mala2["ok"] is False
    buena = reg.responder({"estado": "respondida", "respuesta": "7",
                           "resultados": [{"clave": "n", "sql": SQL_V01, "valor": 7}]})
    assert buena == {"ok": True} and reg.final["resultados"][0]["valor"] == 7
    r = reg.parar()
    assert r.estado == "respondida" and r.errores_herramienta == 2 and r.herramientas == 3


def test_parar_por_limite_sin_final():
    reg = Registro("x", H55, tarea("n01-es"))
    reg.modelo({"input_tokens": 1, "output_tokens": 1}, 1)
    r = reg.parar("limite_alcanzado", "max_pasos")
    assert r.final is None and r.motivo == "max_pasos" and contrato.validar_resultado(r) == []


# ---------- trazas ----------

def test_trazas_jsonl_comunes(tmp_path):
    ruta = tmp_path / "t.jsonl"
    reg = Registro("langgraph", H55, {**tarea("n01-es"), "rep": 2}, ruta_trazas=ruta)
    reg.modelo({"input_tokens": 10, "output_tokens": 1}, 12.3, ["describir_esquema"])
    reg.herramienta("describir_esquema", 4.2, '{"ok": true}')
    reg.herramienta("ejecutar_sql", 3.1, {"ok": False, "error": {"tipo": "permiso_denegado"}})
    reg.responder({"estado": "abstenida", "respuesta": "x", "resultados": []})
    reg.parar()
    eventos = [json.loads(x) for x in ruta.read_text().splitlines()]
    assert [e["tipo"] for e in eventos] == ["modelo", "herramienta", "herramienta", "herramienta", "final", "parada"]
    assert all(validar_evento(e) == [] for e in eventos)
    assert {e["framework"] for e in eventos} == {"langgraph"} and {e["tarea"] for e in eventos} == {"n01-es#2"}
    assert eventos[2]["error"] == "permiso_denegado" and eventos[0]["tokens_in"] == 10


def test_traza_rechaza_eventos_incompletos():
    t = Trazador(None, "x", H55, "c", "t")
    with pytest.raises(ValueError):
        t("modelo", 1, ms=1)
    with pytest.raises(ValueError):
        t("otro", 1)


# ---------- modelo simulado ----------

def _post(base, cuerpo):
    req = urllib.request.Request(base + "/v1/messages", data=json.dumps(cuerpo).encode(),
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return r.read().decode()


def test_doble_sigue_el_guion_con_y_sin_streaming():
    g = Guion([Turno([herramienta("ejecutar_sql", {"sql": "SELECT 1"})], 11, 2), Turno([texto("listo")], 13, 3)])
    with DobleAnthropic(g) as d:
        m1 = json.loads(_post(d.base_url, {"model": H55, "messages": []}))
        sse = _post(d.base_url, {"model": H55, "messages": [], "stream": True})
        fin = json.loads(_post(d.base_url, {"model": H55, "messages": []}))
    assert m1["stop_reason"] == "tool_use" and m1["content"][0]["input"] == {"sql": "SELECT 1"}
    assert m1["usage"] == {"input_tokens": 11, "output_tokens": 2}
    datos = [json.loads(x[6:]) for x in sse.splitlines() if x.startswith("data: ")]
    assert datos[0]["type"] == "message_start" and datos[-1]["type"] == "message_stop"
    assert any(x.get("delta", {}).get("text") == "listo" for x in datos)
    assert fin["content"][0]["text"] == "(fin del guion)" and len(g.peticiones) == 3


# ---------- verificador sobre salidas guionadas (servidor MCP de la semana 14 + loop propio) ----------

def _correr(entorno, t, guion):
    from agente.verificar import verificar  # noqa: F401  (semana 13)
    srv = entorno.servidores["normal"]
    with DobleAnthropic(guion) as d:
        a = AdaptadorPropio(srv.url, entorno.token("analista"), base_url=d.base_url)
        r = a.resolver(t)
    return r, a.ultimas_trazas, guion


def test_guion_correcto_pasa_el_verificador(entorno, adm, conexion_verificador):
    from agente.verificar import verificar
    t = tarea("v01-es", adm)
    valor = adm.execute(SQL_V01.replace("artmst", "legado.artmst").replace("prvmst", "legado.prvmst")).fetchone()[0]
    r, eventos, g = _correr(entorno, t, guion_respuesta(t, [{"clave": "n", "sql": SQL_V01, "valor": valor}]))
    assert r.estado == "respondida" and contrato.validar_resultado(r, t) == []
    v = verificar(t, r.final, conexion_verificador, r.estado)
    assert v["exito"] and v["exactitud_claves"] == 1 and v["coherencia_claves"] == 1
    # costo = suma exacta de los tokens del guion; pasos = turnos del guion
    tin, tout = sum(x.tokens_in for x in g.turnos), sum(x.tokens_out for x in g.turnos)
    assert (r.pasos, r.tokens_in, r.tokens_out) == (len(g.turnos), tin, tout)
    assert math.isclose(r.costo_usd, contrato.costo(H55, tin, tout))
    assert [e["tipo"] for e in eventos].count("modelo") == len(g.turnos) and eventos[-1]["tipo"] == "parada"
    assert all(validar_evento(e) == [] for e in eventos) and {e["framework"] for e in eventos} == {"propio"}
    # el loop recibió el prompt y la herramienta responder de la semana 13
    import agente.loop as l13
    assert g.peticiones[0]["system"] == l13.SISTEMA and g.peticiones[0]["model"] == H55
    assert {x["name"] for x in g.peticiones[0]["tools"]} >= {"ejecutar_sql", "responder"}


def test_guion_con_sql_equivocado_falla_el_verificador(entorno, adm, conexion_verificador):
    from agente.verificar import verificar
    t = tarea("v01-es", adm)
    malo = SQL_V01.replace("'US'", "'MX'")
    r, _, _ = _correr(entorno, t, guion_respuesta(t, [{"clave": "n", "sql": malo, "valor": 7}]))
    v = verificar(t, r.final, conexion_verificador, r.estado)
    assert r.estado == "respondida" and not v["exito"] and v["exactitud_claves"] == 0


def test_abstencion_y_aclaracion_guionadas(entorno, adm, conexion_verificador):
    from agente.verificar import verificar
    for id_ in ("n01-es", "a01-es"):
        t = tarea(id_, adm)
        r, _, _ = _correr(entorno, t, guion_respuesta(t))
        assert r.estado == t["estado_esperado"] and verificar(t, r.final, conexion_verificador, r.estado)["exito"]
    t = tarea("n01-es", adm)   # responder lo que no se pidió: abstenida esperada, respondida entregada
    r, _, _ = _correr(entorno, t, guion_respuesta(t, estado="requiere_aclaracion"))
    assert not verificar(t, r.final, conexion_verificador, r.estado)["exito"]


def test_guion_sin_responder_termina_en_limite(entorno, adm):
    t = tarea("v01-es", adm)
    r, eventos, _ = _correr(entorno, t, Guion([Turno([texto("pienso")]), Turno([texto("sigo pensando")])]))
    assert r.estado == "limite_alcanzado" and r.motivo == "sin_responder" and r.final is None
    assert contrato.validar_resultado(r, t) == []


# ---------- puente entre procesos ----------

def test_puente_trabajador_devuelve_el_mismo_contrato(entorno, adm):
    from arnes.puente import Puente
    t = tarea("n01-es", adm)
    g = guion_respuesta(t)
    with DobleAnthropic(g) as d, Puente("propio") as p:
        out = p.resolver(tarea=t, mcp_url=entorno.servidores["normal"].url, token=entorno.token("analista"),
                         base_url=d.base_url)
    assert "error" not in out, out
    r = contrato.resultado_de_dict(out["resultado"])
    assert r.estado == "abstenida" and contrato.validar_resultado(r, t) == []
    assert all(validar_evento(e) == [] for e in out["eventos"]) and out["eventos"][-1]["tipo"] == "parada"


# ---------- el contrato se carga igual en el entorno de cada framework ----------

PROG = """
import hashlib, json, sys
sys.path.insert(0, {s15!r})
from arnes import contrato
from arnes.adaptador import Registro
l = contrato.semana13()
reg = Registro("x", "claude-haiku-5-5", {{"id": "n01-es", "tarea": "x", "estado_esperado": "abstenida"}})
reg.modelo({{"inputTokens": 1200, "outputTokens": 300}}, 1)
reg.responder({{"estado": "abstenida", "respuesta": "x", "resultados": []}})
r = reg.parar()
print(json.dumps({{"sistema": hashlib.sha256(l.SISTEMA.encode()).hexdigest(), "costo": r.costo_usd,
                  "problemas": contrato.validar_resultado(r)}}))
"""


@pytest.mark.parametrize("venv", ["lg", "st", "oa", "adk"])
def test_contrato_en_el_entorno_de_cada_framework(venv):
    py = VENVS / venv / "bin" / "python"
    if not py.exists():
        pytest.skip(f"sin el entorno {venv} (linea_base/preparar.sh)")
    p = subprocess.run([str(py), "-c", PROG.format(s15=str(S15))], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-800:]
    out = json.loads(p.stdout.strip().splitlines()[-1])
    import agente.loop as l13
    assert out["sistema"] == hashlib.sha256(l13.SISTEMA.encode()).hexdigest()
    assert math.isclose(out["costo"], 0.00027) and out["problemas"] == []
