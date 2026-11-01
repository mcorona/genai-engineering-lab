"""Actividad 5 (sin API): pasarela con las defensas de la semana 14 para cualquier framework y métricas del reporte."""
import importlib.util
import json

import pytest
from conftest import S14, S15, VENVS, tarea

from arnes.puente import Puente
from arnes.simulado import DobleAnthropic, Guion, Turno, herramienta
from eval import correr

pytestmark_venvs = pytest.mark.skipif(not all((VENVS / v / "bin" / "python").exists() for v in ("lg", "st")),
                                      reason="sin los entornos de LangGraph y Strands")


def test_wilson_y_bootstrap():
    assert correr.wilson(36, 40) == (0.769, 0.96)            # mismo valor que la actividad 7 de la semana 14
    assert correr.wilson(0, 0)[0] != correr.wilson(0, 0)[0]    # nan
    a = {"t1": [True, True, True], "t2": [False, False, False]}
    b = {"t1": [True, True, True], "t2": [False, False, False], "t3": [True]}
    c = correr.bootstrap_pareado(a, b, reps=200)
    assert c == {"n_tareas": 2, "diferencia": 0.0, "ic95": (0.0, 0.0)}
    d = correr.bootstrap_pareado({"t1": [True], "t2": [True]}, {"t1": [False], "t2": [False]}, reps=200)
    assert d["diferencia"] == 1.0 and d["ic95"] == (1.0, 1.0)


def test_resumen_y_pass3():
    filas = [{"id": "x", "exito": e, "tipo": "simple", "estado": "respondida", "costo_usd": 0.001, "tokens_in": 10,
              "tokens_out": 1, "segundos": 1.0, "pasos": 2, "herramientas": 3} for e in (True, True, False)]
    filas += [{**filas[0], "id": "y"} for _ in range(3)]
    r = correr.resumen(filas)
    assert r["pass1"] == round(5 / 6, 3) and r["pass3"] == 0.5 and r["por_tipo"]["simple"] == "5/6"


def test_costo_de_desarrollo_cuenta_codigo_y_dependencias():
    d = correr.costo_desarrollo()
    assert d["langgraph"]["lineas_codigo"] > 50 and d["strands"]["lineas_codigo"] > 50
    assert any(x.startswith("langgraph==") for x in d["langgraph"]["dependencias_directas"])
    assert any(x.startswith("strands-agents") for x in d["strands"]["dependencias_directas"])


@pytest.fixture(scope="module")
def seg(entorno):
    spec = importlib.util.spec_from_file_location("seguridad14_test15", S14 / "seguridad" / "correr.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytestmark_venvs
@pytest.mark.parametrize("fw", ["langgraph", "strands"])
def test_pasarela_lleva_las_defensas_a_cada_framework(fw, entorno, seg):
    """Caso de shadowing: inventario_plus (fuera de la allowlist) publica su propio ejecutar_sql. A través de la pasarela
    el framework solo ve las herramientas prefijadas del servidor legítimo; un intento de llamar a la sombra no llega a
    ella, y cada resultado llega envuelto en untrusted_data con su fuente."""
    from eval.pasarela import abrir_pasarela
    caso = next(c for c in seg.casos() if c["id"] == "sh-1-es")
    cliente, mal = seg.preparar(caso, entorno, defensas=True)
    guion = Guion([Turno([herramienta("legado__ejecutar_sql", {"sql": "SELECT count(*) AS n FROM artmst WHERE art_crt"})]),
                   Turno([herramienta("inventario_plus__ejecutar_sql", {"sql": "SELECT 1"})]),
                   Turno([herramienta("ejecutar_sql", {"sql": "SELECT 1"})]),
                   Turno([herramienta("responder", {"estado": "respondida", "respuesta": "30", "resultados": []})])])
    with cliente, DobleAnthropic(guion) as d, Puente(fw) as p:
        nombres = {x["name"] for x in cliente.definiciones()}
        gw = abrir_pasarela(cliente)
        try:
            out = p.resolver(tarea={"id": caso["id"], "tarea": caso["tarea"]}, mcp_url=gw.url, token="pasarela",
                             base_url=d.base_url, opciones={"aprobacion": None, "sistema": seg.SISTEMA_14})
        finally:
            gw.cerrar()
        ev = seg.evaluar(caso, __import__("arnes.contrato", fromlist=["x"]).resultado_de_dict(out["resultado"]),
                         cliente, mal)
    assert "error" not in out, out.get("error")
    assert nombres and all(n.startswith("legado__") for n in nombres)
    herramientas_modelo = {t["name"] for t in guion.peticiones[0]["tools"]}
    assert herramientas_modelo == nombres | {"responder"}                        # el modelo solo ve lo de la pasarela
    sistema = guion.peticiones[0]["system"]
    sistema = "".join(b["text"] for b in sistema) if isinstance(sistema, list) else sistema
    assert sistema == seg.SISTEMA_14 and "untrusted_data" in sistema
    eventos = [e for e in out["eventos"] if e["tipo"] == "herramienta"]
    assert [e["herramienta"] for e in eventos][:3] == ["legado__ejecutar_sql", "inventario_plus__ejecutar_sql", "ejecutar_sql"]
    assert eventos[0]["ok"] and not eventos[1]["ok"] and not eventos[2]["ok"]
    assert [x["servidor"] for x in cliente.llamadas] == ["legado"]              # solo la llamada legítima salió
    salida = json.loads(cliente.llamadas[0]["salida"])
    assert salida["ok"] and salida["filas"]
    vuelta = json.dumps(guion.peticiones[1]["messages"][-1], ensure_ascii=False)   # lo que el modelo recibió
    assert "untrusted_data" in vuelta and "legado.ejecutar_sql" in vuelta
    assert ev["llamo_a_la_sombra"] is False and ev["ok"] and mal["inventario_plus"].capturas == []
