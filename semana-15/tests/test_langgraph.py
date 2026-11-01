"""Actividad 3: el agente en LangGraph contra el loop propio de la semana 13, con el mismo modelo simulado y el mismo
servidor MCP de la semana 14. Equivalencia de contrato, límites, checkpoints e interrupción. Sin API ($0)."""
import math

import pytest
from conftest import VENVS, tarea

from arnes import contrato
from arnes.puente import Puente
from arnes.simulado import DobleAnthropic, Guion, Turno, guion_respuesta, herramienta, texto
from arnes.trazas import validar_evento

pytestmark = pytest.mark.skipif(not (VENVS / "lg" / "bin" / "python").exists(),
                                reason="sin el entorno de LangGraph (linea_base/preparar.sh)")

SQL_V01 = ("SELECT COUNT(*) AS numero FROM artmst a JOIN prvmst p ON p.prv_id = a.art_prv "
           "WHERE a.art_lin = 'Tornilleria' AND p.prv_pais = 'US'")
CAMPOS = ("estado", "final", "pasos", "herramientas", "tokens_in", "tokens_out", "errores_herramienta", "motivo",
          "turnos_paralelos")


@pytest.fixture(scope="module")
def puentes():
    with Puente("propio") as p, Puente("langgraph") as lg:
        yield {"propio": p, "langgraph": lg}


def _sistema(cuerpo):
    s = cuerpo.get("system")
    return "".join(b.get("text", "") for b in s) if isinstance(s, list) else s


def correr(puente, entorno, t, guion, limites=None, opciones=None, usuario="analista"):
    srv = entorno.servidores["normal"]
    antes = len(srv.trazas.ultimas)
    with DobleAnthropic(guion) as d:
        out = puente.resolver(tarea=t, mcp_url=srv.url, token=entorno.token(usuario), base_url=d.base_url,
                              limites=limites, opciones=opciones)
    assert "error" not in out, out.get("error")
    llamadas = [x["nombre"] for x in srv.trazas.ultimas[antes:] if x.get("metodo") == "tools/call"]
    return contrato.resultado_de_dict(out["resultado"]), out, guion.peticiones, llamadas


def ambos(puentes, entorno, t, fabrica, limites=None):
    return {fw: correr(p, entorno, t, fabrica(), limites, {} if fw == "propio" else {"aprobacion": None})
            for fw, p in puentes.items()}


def _v01(adm):
    t = tarea("v01-es", adm)
    valor = adm.execute(SQL_V01.replace("artmst", "legado.artmst").replace("prvmst", "legado.prvmst")).fetchone()[0]
    return t, valor


# ---------- equivalencia de contrato ----------

@pytest.mark.parametrize("caso", ["correcta", "sql_equivocado", "abstencion", "aclaracion", "sin_responder",
                                  "respuesta_invalida_y_corregida", "responder_acompanado"])
def test_equivalencia_con_el_loop_propio(puentes, entorno, adm, conexion_verificador, caso):
    from agente.verificar import verificar
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
        "responder_acompanado": lambda: Guion([
            Turno([herramienta("describir_esquema", {}), herramienta("responder", {"estado": "abstenida",
                                                                                   "respuesta": "x", "resultados": []})]),
            Turno([herramienta("responder", {"estado": "respondida", "respuesta": "7",
                                             "resultados": [{"clave": "n", "sql": SQL_V01, "valor": valor}]})])]),
    }
    res = ambos(puentes, entorno, t, fabricas[caso])
    (rp, _, pp, lp), (rl, out, pl, ll) = res["propio"], res["langgraph"]
    for campo in CAMPOS:
        assert getattr(rl, campo) == getattr(rp, campo), (caso, campo, getattr(rl, campo), getattr(rp, campo))
    assert math.isclose(rl.costo_usd, rp.costo_usd) and contrato.validar_resultado(rl, t) == []
    assert verificar(t, rl.final, conexion_verificador, rl.estado)["exito"] == \
        verificar(t, rp.final, conexion_verificador, rp.estado)["exito"]
    assert ll == lp                                        # mismas llamadas al servidor MCP, en el mismo orden
    assert len(pl) == len(pp)                              # mismas llamadas al modelo
    for a, b in zip(pl, pp):                               # mismo prompt, modelo, esfuerzo, tokens y herramientas
        assert _sistema(a) == _sistema(b) and a["model"] == b["model"] == "claude-haiku-5-5"
        assert a["max_tokens"] == b["max_tokens"] and a.get("output_config") == b.get("output_config") == {"effort": "low"}
        assert sorted(x["name"] for x in a["tools"]) == sorted(x["name"] for x in b["tools"])
    assert pl[0]["messages"][0]["content"] in (pp[0]["messages"][0]["content"],
                                               [{"type": "text", "text": pp[0]["messages"][0]["content"]}])
    assert all(validar_evento(e) == [] for e in out["eventos"]) and {e["framework"] for e in out["eventos"]} == {"langgraph"}
    assert [e["tipo"] for e in out["eventos"]].count("modelo") == rl.pasos


# ---------- límites de la semana 13 ----------

@pytest.mark.parametrize("limites,motivo", [
    ({"max_pasos": 2}, "max_pasos"),
    ({"max_herramientas": 1}, "max_herramientas"),
    ({"max_tokens_total": 2000}, "max_tokens_total"),
])
def test_limites_iguales_al_loop_propio(puentes, entorno, adm, limites, motivo):
    t, valor = _v01(adm)
    fabrica = lambda: guion_respuesta(t, [{"clave": "n", "sql": SQL_V01, "valor": valor}])  # noqa: E731
    res = ambos(puentes, entorno, t, fabrica, limites)
    (rp, *_), (rl, *_) = res["propio"], res["langgraph"]
    assert rp.estado == rl.estado == "limite_alcanzado" and rp.motivo == rl.motivo == motivo
    assert (rl.pasos, rl.herramientas, rl.tokens_in) == (rp.pasos, rp.herramientas, rp.tokens_in)
    assert rl.final is None and contrato.validar_resultado(rl, t) == []


def test_tres_errores_seguidos_paran_igual(puentes, entorno, adm):
    t, _ = _v01(adm)
    fabrica = lambda: Guion([Turno([herramienta("ejecutar_sql", {"sql": "SELECT * FROM no_existe"})])] * 4)  # noqa: E731
    res = ambos(puentes, entorno, t, fabrica)
    (rp, *_), (rl, *_) = res["propio"], res["langgraph"]
    assert rp.motivo == rl.motivo == "errores_herramienta" and rl.errores_herramienta == rp.errores_herramienta == 3


# ---------- human-in-the-loop y checkpoints ----------

def _guion_propuesta():
    return Guion([Turno([herramienta("proponer_orden_compra", {"sku": "SKU-0001", "cantidad": 10,
                                                                  "motivo": "prueba de human-in-the-loop"})]),
                  Turno([herramienta("responder", {"estado": "abstenida", "respuesta": "x", "resultados": []})])])


@pytest.mark.parametrize("decision", ["aprobar", "rechazar"])
def test_interrupcion_antes_de_proponer(puentes, entorno, adm, decision):
    t = tarea("n01-es", adm)
    r, out, _, llamadas = correr(puentes["langgraph"], entorno, t, _guion_propuesta(), opciones={"aprobacion": decision})
    ex = out["extra"]
    assert len(ex["pausas"]) == 1 and ex["pausas"][0]["herramienta"] == "proponer_orden_compra"
    assert ex["pausas"][0]["argumentos"]["sku"] == "SKU-0001"
    assert ex["decisiones"] == [{"herramienta": "proponer_orden_compra", "decision": decision}]
    assert ex["checkpoints"] >= 4 and r.estado == "abstenida"
    if decision == "aprobar":
        assert llamadas == ["proponer_orden_compra"] and r.errores_herramienta == 0
    else:   # rechazada: no llega al servidor y el modelo la recibe como error
        assert llamadas == [] and r.errores_herramienta == 1
        evento = next(e for e in out["eventos"] if e.get("herramienta") == "proponer_orden_compra")
        assert evento["error"] == "rechazada_por_humano"


def test_sin_politica_no_interrumpe(puentes, entorno, adm):
    t = tarea("n01-es", adm)
    r, out, _, llamadas = correr(puentes["langgraph"], entorno, t, _guion_propuesta(), opciones={"aprobacion": None})
    assert out["extra"]["pausas"] == [] and llamadas == ["proponer_orden_compra"]


def test_perfil_sin_scope_de_compras_ni_siquiera_llega_a_la_pausa(puentes, entorno, adm):
    """El almacenista no tiene legado:compras:proponer: el servidor no le lista la herramienta, así que no hay nada que
    aprobar y la llamada no llega al servidor. La aprobación humana nunca sustituye a los permisos."""
    t = tarea("n01-es", adm)
    r, out, _, llamadas = correr(puentes["langgraph"], entorno, t, _guion_propuesta(), opciones={"aprobacion": "aprobar"},
                                 usuario="almacenista")
    evento = next(e for e in out["eventos"] if e.get("herramienta") == "proponer_orden_compra")
    assert out["extra"]["pausas"] == [] and llamadas == []
    assert evento["ok"] is False and evento["error"] == "herramienta_desconocida" and r.errores_herramienta == 1
