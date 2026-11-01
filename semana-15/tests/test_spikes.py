"""Actividad 6: los spikes (OpenAI Agents SDK y Google ADK, con Claude por LiteLLM) contra el loop propio de la semana 13,
con el mismo modelo simulado y el mismo servidor MCP. Las diferencias de cada framework quedan registradas como prueba
(no se ocultan). Sin API ($0)."""
import math

import pytest
from conftest import VENVS, tarea
from test_equivalencia import SQL_V01, _sistema, _v01, correr

from arnes import contrato
from arnes.puente import Puente
from arnes.simulado import Guion, Turno, guion_respuesta, herramienta, texto

SPIKES = ["openai_agents", "google_adk"]
pytestmark = pytest.mark.skipif(not all((VENVS / v / "bin" / "python").exists() for v in ("oa", "adk")),
                                reason="sin los entornos de OpenAI Agents y ADK (linea_base/preparar.sh)")
CAMPOS = ("estado", "final", "pasos", "herramientas", "tokens_in", "tokens_out", "errores_herramienta", "motivo")


@pytest.fixture(scope="module")
def todos():
    with Puente("propio") as p, Puente("openai_agents") as oa, Puente("google_adk") as adk:
        yield {"propio": p, "openai_agents": oa, "google_adk": adk}


@pytest.mark.parametrize("fw", SPIKES)
@pytest.mark.parametrize("caso", ["correcta", "sql_equivocado", "abstencion", "aclaracion", "sin_responder",
                                  "respuesta_invalida_y_corregida", "max_pasos"])
def test_spike_equivale_al_loop_propio(todos, entorno, adm, conexion_verificador, fw, caso):
    from agente.verificar import verificar
    import agente.loop as l13
    t, valor = _v01(adm)
    if caso in ("abstencion", "aclaracion"):
        t = tarea("n01-es" if caso == "abstencion" else "a01-es", adm)
    fabricas = {
        "correcta": lambda: guion_respuesta(t, [{"clave": "n", "sql": SQL_V01, "valor": valor}]),
        "sql_equivocado": lambda: guion_respuesta(t, [{"clave": "n", "sql": SQL_V01.replace("'US'", "'MX'"), "valor": 7}]),
        "abstencion": lambda: guion_respuesta(t),
        "aclaracion": lambda: guion_respuesta(t),
        "sin_responder": lambda: Guion([Turno([texto("pienso")]), Turno([texto("sigo")])]),
        "respuesta_invalida_y_corregida": lambda: Guion([
            Turno([herramienta("responder", {"estado": "respondida", "respuesta": "7", "resultados": []})]),
            Turno([herramienta("responder", {"estado": "respondida", "respuesta": "7",
                                             "resultados": [{"clave": "n", "sql": SQL_V01, "valor": valor}]})])]),
        "max_pasos": lambda: guion_respuesta(t, [{"clave": "n", "sql": SQL_V01, "valor": valor}]),
    }
    limites = {"max_pasos": 2} if caso == "max_pasos" else None
    rp, _, pp, lp = correr(todos["propio"], entorno, t, fabricas[caso](), limites, {})
    rs, out, ps, ls = correr(todos[fw], entorno, t, fabricas[caso](), limites, {})
    for campo in CAMPOS:
        assert getattr(rs, campo) == getattr(rp, campo), (fw, caso, campo, getattr(rs, campo), getattr(rp, campo))
    assert math.isclose(rs.costo_usd, rp.costo_usd) and contrato.validar_resultado(rs, t) == []
    assert verificar(t, rs.final, conexion_verificador, rs.estado)["exito"] == \
        verificar(t, rp.final, conexion_verificador, rp.estado)["exito"]
    assert ls == lp and len(ps) == len(pp)
    for a in ps:
        assert a["model"] == "claude-haiku-5-5" and a["max_tokens"] == 4000 and a.get("output_config") == {"effort": "low"}
        assert "extra_body" not in a                                  # LiteLLM no debe mandar la clave literal
        assert sorted(x["name"] for x in a["tools"]) == sorted(x["name"] for x in pp[0]["tools"])
        if fw == "openai_agents":
            assert _sistema(a) == l13.SISTEMA
        else:   # ADK agrega su línea de identidad al prompt de sistema (fricción documentada)
            assert _sistema(a).startswith(l13.SISTEMA) and "Your internal name is" in _sistema(a)
    assert {e["framework"] for e in out["eventos"]} == {fw}
