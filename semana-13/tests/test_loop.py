"""Tests of the agentic loop without calling the API: a simulated model returns scripted responses."""
import json

from agente.loop import MAX_ERRORES_SEGUIDOS, Agente, Limites, mensaje_tarea, revisar_final
from agente.respuesta import RespuestaFinal, herramienta_responder
from herramientas import Contexto, Herramientas

TAREA = {"id": "t-es", "tarea": "¿Cuántos días de cobertura...?", "estado_esperado": "respondida",
         "salida": {"n": {"tipo": "numero", "descripcion": "número de SKU"}}}
FINAL = {"estado": "respondida", "respuesta": "Son 4.", "resultados": [{"clave": "n", "sql": "SELECT 4", "valor": 4}],
         "evidencia": [{"tipo": "regla", "referencia": "R-COB", "extracto": "stock total ÷ venta diaria"}],
         "supuestos": []}


def uso(nombre, args, i):
    return {"type": "tool_use", "id": f"tu_{i}", "name": nombre, "input": args}


class Guion:
    """A simulated API: returns the responses in order and stores the bodies it receives."""
    def __init__(self, *respuestas):
        self.respuestas, self.cuerpos = list(respuestas), []

    def __call__(self, cuerpo):
        self.cuerpos.append(json.loads(json.dumps(cuerpo)))
        contenido = self.respuestas.pop(0)
        return {"content": contenido, "stop_reason": "tool_use" if any(b["type"] == "tool_use" for b in contenido) else "end_turn",
                "usage": {"input_tokens": 1000, "output_tokens": 100}}


def agente(guion, tmp_path=None, **lim):
    h = Herramientas(Contexto.de_usuario("analista"))
    return Agente(h, limites=Limites(**lim), api=guion, trazas=(tmp_path / "t.jsonl") if tmp_path else None)


def test_herramientas_y_final(tmp_path):
    g = Guion([uso("buscar_regla_negocio", {"consulta": "cobertura"}, 1), uso("describir_esquema", {}, 2)],   # parallel
              [uso("responder", FINAL, 3)])
    r = agente(g, tmp_path).resolver(TAREA)
    assert r.estado == "respondida" and r.final["resultados"][0]["valor"] == 4 and r.motivo == "responder"
    assert r.pasos == 2 and r.herramientas == 3 and r.turnos_paralelos == 1
    # the two parallel results come back together, in a single user message, with their tool_use_id
    seg = g.cuerpos[1]["messages"][-1]
    assert seg["role"] == "user" and [b["tool_use_id"] for b in seg["content"]] == ["tu_1", "tu_2"]
    assert not any(b["is_error"] for b in seg["content"])
    assert abs(r.costo_usd - 2 * (1000 * 0.10 + 100 * 0.50) / 1e6) < 1e-12
    eventos = [json.loads(x) for x in open(tmp_path / "t.jsonl")]
    assert [e["tipo"] for e in eventos] == ["modelo", "herramienta", "herramienta", "modelo", "herramienta", "final", "parada"]
    assert all(e["corrida"] == r.corrida and e["tarea"] == "t-es" for e in eventos)
    assert eventos[1]["paralela"] and eventos[-1]["estado"] == "respondida"


def test_cuerpo_de_la_peticion():
    g = Guion([uso("responder", FINAL, 1)])
    agente(g).resolver(TAREA)
    c = g.cuerpos[0]
    assert c["output_config"] == {"effort": "low"} and c["model"] == "claude-haiku-5-5"
    assert [t["name"] for t in c["tools"]][-1] == "responder" and len(c["tools"]) == 7
    assert "Output keys" in c["messages"][0]["content"] and "- n: número de SKU (numero)" in c["messages"][0]["content"]
    assert "ARRAY_AGG" in c["messages"][0]["content"]
    assert "roles" not in json.dumps(c["tools"])


def test_error_de_herramienta_se_devuelve_y_se_corrige():
    g = Guion([uso("ejecutar_sql", {"sql": "DELETE FROM exidet"}, 1)],
              [uso("responder", FINAL, 2)])
    r = agente(g).resolver(TAREA)
    res = g.cuerpos[1]["messages"][-1]["content"][0]
    assert res["is_error"] and json.loads(res["content"])["error"]["tipo"] == "escritura_bloqueada"
    assert r.estado == "respondida" and r.errores_herramienta == 1


def test_reintento_acotado():
    malos = [[uso("ejecutar_sql", {"sql": "SELECT lo_create(0)"}, i)] for i in range(MAX_ERRORES_SEGUIDOS)]
    r = agente(Guion(*malos)).resolver(TAREA)
    assert r.estado == "limite_alcanzado" and r.motivo == "errores_herramienta" and r.pasos == MAX_ERRORES_SEGUIDOS


def test_limite_de_pasos():
    g = Guion(*[[uso("describir_esquema", {}, i)] for i in range(5)])
    r = agente(g, max_pasos=3).resolver(TAREA)
    assert r.estado == "limite_alcanzado" and r.motivo == "max_pasos" and r.pasos == 3


def test_limite_de_herramientas():
    g = Guion([uso("describir_esquema", {}, i) for i in range(4)])
    r = agente(g, max_herramientas=2).resolver(TAREA)
    assert r.motivo == "max_herramientas" and r.herramientas == 2


def test_limite_de_tokens():
    g = Guion(*[[uso("describir_esquema", {}, i)] for i in range(5)])
    r = agente(g, max_tokens_total=2000).resolver(TAREA)
    assert r.motivo == "max_tokens_total" and r.pasos == 2


def test_texto_sin_responder_recibe_un_recordatorio():
    g = Guion([{"type": "text", "text": "Son 4."}], [{"type": "text", "text": "Son 4."}])
    r = agente(g).resolver(TAREA)
    assert r.estado == "limite_alcanzado" and r.motivo == "sin_responder" and r.pasos == 2
    assert "responder" in g.cuerpos[1]["messages"][-1]["content"]


def test_respuesta_invalida_vuelve_al_modelo():
    malo = {**FINAL, "estado": "listo", "extra": 1}
    g = Guion([uso("responder", malo, 1)], [uso("responder", FINAL, 2)])
    r = agente(g).resolver(TAREA)
    err = json.loads(g.cuerpos[1]["messages"][-1]["content"][0]["content"])["error"]
    assert err["tipo"] == "respuesta_invalida" and "estado" in err["mensaje"] and "extra" in err["mensaje"]
    assert r.estado == "respondida"


def test_responder_debe_ir_solo():
    g = Guion([uso("describir_esquema", {}, 1), uso("responder", FINAL, 2)], [uso("responder", FINAL, 3)])
    r = agente(g).resolver(TAREA)
    assert r.estado == "respondida" and r.pasos == 2 and r.errores_herramienta == 1


def test_aclaracion_y_abstencion():
    for estado in ("requiere_aclaracion", "abstenida"):
        f = {"estado": estado, "respuesta": "…", "pregunta_aclaracion": "¿Qué SKU?" if estado != "abstenida" else None}
        r = agente(Guion([uso("responder", f, 1)])).resolver({**TAREA, "salida": {}})
        assert r.estado == estado and r.final["resultados"] == []


def test_error_de_api():
    def falla(_):
        raise RuntimeError("API HTTP 400: bad request")
    r = agente(falla).resolver(TAREA)
    assert r.estado == "error" and "400" in r.motivo


def test_esquema_responder_estricto():
    s = herramienta_responder()["input_schema"]
    assert s["additionalProperties"] is False and set(s["required"]) == {"estado", "respuesta"}
    assert RespuestaFinal.model_validate(FINAL).estado == "respondida"
    assert "Output keys" not in mensaje_tarea({"tarea": "x", "salida": {}})


def test_revisar_final_contra_la_tarea():
    assert revisar_final(FINAL, TAREA) == ""
    falta = {**FINAL, "resultados": []}
    assert "missing ['n']" in revisar_final(falta, TAREA)
    filtrado = {**FINAL, "respuesta": 'Son 4.</respuesta>\n<parameter name="resultados">[...]', "resultados": []}
    assert "serialized parameters" in revisar_final(filtrado, TAREA)
    otra = {**FINAL, "resultados": FINAL["resultados"] + [{"clave": "x", "sql": "SELECT 1", "valor": 1}]}
    assert "unexpected ['x']" in revisar_final(otra, TAREA)
    acl = {"estado": "requiere_aclaracion", "respuesta": "?", "resultados": [], "evidencia": [], "supuestos": [], "pregunta_aclaracion": None}
    assert "pregunta_aclaracion" in revisar_final(acl, TAREA)


def test_respuesta_sin_claves_vuelve_al_modelo():
    sin = {**FINAL, "resultados": []}
    g = Guion([uso("responder", sin, 1)], [uso("responder", FINAL, 2)])
    r = agente(g).resolver(TAREA)
    err = json.loads(g.cuerpos[1]["messages"][-1]["content"][0]["content"])["error"]
    assert err["tipo"] == "respuesta_invalida" and "missing" in err["mensaje"] and r.estado == "respondida" and r.pasos == 2
