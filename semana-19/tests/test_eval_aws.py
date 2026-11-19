"""Week 19, activity 8: the eval against the deployed endpoint, offline (no AWS: every client is a fake)."""
from __future__ import annotations

import ast
import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
RAIZ = S19.parent
sys.path.insert(0, str(S19))


def _cargar():
    spec = importlib.util.spec_from_file_location("eval_aws", S19 / "eval" / "eval_aws.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


E = _cargar()
C = E.C
SQL_OK = "SELECT art_cd FROM legado.artmst WHERE art_cd = 'SKU-0009'"
JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJhYmMifQ.c2lnbmF0dXJh"


def tarea(id_="s03-es", idioma="es", esperado=(("SKU-0009",),)):
    return {"id": id_, "idioma": idioma, "tarea": "¿Qué SKU?", "estado_esperado": "respondida", "tipo": "simple",
            "salida": {"filas": {"tipo": "filas", "descripcion": "lo pedido", "orden": False, "sql_ref": "SELECT 1",
                                 "esperado": [list(f) for f in esperado]}}}


class Http:
    """The questions API: 202, then 'en_curso' once, then the answer. No token: 401. The analyst on /aprobaciones: 403."""

    def __init__(self, final=None):
        self.id, self.pedidos, self.gets = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0", [], 0
        self.final = final or {"id": self.id, "estado": "respondida", "respuesta": "SKU-0009", "decisiones": [],
                               "resultados": [{"clave": "filas", "sql": SQL_OK, "valor": [["SKU-0009"]]}]}

    def __call__(self, metodo, ruta, token, cuerpo):
        self.pedidos.append((metodo, ruta, token, cuerpo))
        if token is None:
            return 401, {"message": "Unauthorized"}
        if ruta.startswith("/aprobaciones/"):
            return 403, {"message": "Forbidden"}
        if metodo == "POST":
            return 202, {"id": self.id, "estado": "en_curso"}
        self.gets += 1
        return (200, {"id": self.id, "estado": "en_curso"}) if self.gets < 2 else (200, self.final)


def spans(run_id="0f1e2d3c4b5a", pasos=3):
    herramientas = [
        {"tipo": "execute_tool", "attrs": {"gen_ai.tool.name": "describir_esquema", "gen_ai.tool.type": "function",
                                           "lab.step": 1, "lab.tool.status": "ok", "lab.tool.args.hmac": "a1"}},
        {"tipo": "execute_tool", "attrs": {"gen_ai.tool.name": "ejecutar_sql", "gen_ai.tool.type": "function",
                                           "lab.step": 2, "lab.tool.status": "ok", "lab.tool.args.hmac": "b2"}}]
    agente = {"tipo": "invoke_agent", "attrs": {"lab.run.id": run_id, "lab.run.tokens.input": 16000,
                                                "lab.run.tokens.output": 1200, "lab.run.tokens.cache_read": 0,
                                                "lab.run.tokens.cache_creation": 0, "lab.run.cost_usd": 0.0242,
                                                "lab.run.steps": pasos, "lab.run.tool_calls": 2,
                                                "lab.run.tool_errors": 0, "lab.outcome.reason": "responder"}}
    return herramientas + [agente]


def medir_con(http=None, reloj=None):
    http = http or Http()
    reloj = reloj or iter(range(0, 10_000, 2))
    return lambda t: C.medir_api(t, "directo", token=JWT, http=http, spans_entre=lambda a, b: spans(),
                                 reloj=lambda: next(reloj), dormir=lambda s: None, largo_respuesta=E.LARGO_RESPUESTA)


def ejecutar_ok(sql):
    return {"filas": [["SKU-0009"]], "truncado": False}


REPORTE_FRIO = "REPORT RequestId: x Duration: 9000.1 ms Billed Duration: 9500 ms Memory Size: 512 MB Max Memory Used: 210 MB Init Duration: 1873.42 ms"
REPORTE_CALIENTE = "REPORT RequestId: y Duration: 7000.0 ms Billed Duration: 7000 ms Memory Size: 512 MB Max Memory Used: 211 MB"


# ---------------------------------------------------------------- reused, not copied

def test_las_tareas_son_las_de_ci_de_la_semana_13_en_los_dos_idiomas():
    ts = E.tareas_ci()
    ids = ast.literal_eval(next(n.value for n in ast.parse((RAIZ / "semana-13/ci/eval_ci.py").read_text()).body
                                if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "TAREAS_CI"))
    assert E.TAREAS_CI == ids and len(ts) == 20
    assert sorted(t["id"] for t in ts) == sorted(f"{i}-{l}" for i in ids for l in ("es", "en"))
    assert {t["idioma"] for t in ts if t["id"].endswith("-en")} == {"en"}


def test_cada_tarea_cabe_en_el_limite_del_api():
    from consultas.api import MAX_PREGUNTA
    assert all(len(C.texto_de_la_tarea(t)) <= MAX_PREGUNTA for t in E.tareas_ci() + E.tareas_de_calentamiento())


def test_el_calentamiento_va_fuera_del_subconjunto_de_ci_y_cabe_en_la_concurrencia_del_agente():
    frio = E.tareas_de_calentamiento()
    assert [t["id"] for t in frio] == list(E.FRIO) and not {t["id"] for t in frio} & {t["id"] for t in E.tareas_ci()}
    assert len(frio) <= 2   # the agent's reserved concurrency (ADR 0012, infra/cdk/app.py)


def test_el_umbral_es_la_regla_de_la_semana_10():
    assert (round(E.umbral_de(1.0, 20), 2), round(E.umbral_de(1.0, 10), 2), round(E.umbral_de(0.9, 10), 2)) == (0.95, 0.90, 0.80)
    r = E.regla_semana10(0.90, 1.0, 20)
    assert r["umbral"] == 0.95 and r["regresion"] is True
    assert E.regla_semana10(0.95, 1.0, 20)["regresion"] is False


def test_wilson_es_el_de_la_semana_3():
    bajo, alto = E.wilson(18, 20)
    assert 0.68 < bajo < 0.70 and 0.97 < alto < 0.98
    assert E.wilson(20, 20)[1] == pytest.approx(1.0)


def test_los_topes_estan_en_el_codigo():
    assert (E.TOPE_USD, E.TOPE_TOKENS) == (1.20, 800_000)


# ---------------------------------------------------------------- expected rows recomputed

def test_los_esperados_se_piden_por_tarea_y_clave_y_reemplazan_los_congelados():
    t = tarea()
    assert E.consultas_esperadas([t]) == {"s03-es/filas": "SELECT 1"}
    (nueva,) = E.con_esperados([t], {"s03-es/filas": [["SKU-0001"]]})
    assert nueva["salida"]["filas"]["esperado"] == [["SKU-0001"]] and t["salida"]["filas"]["esperado"] == [["SKU-0009"]]


# ---------------------------------------------------------------- the API client

def test_el_cliente_manda_la_tarea_espera_el_202_y_sondea_hasta_la_respuesta():
    http = Http()
    f = medir_con(http)(tarea())
    assert http.pedidos[0][:2] == ("POST", "/consultas") and http.pedidos[0][3] == {"pregunta": C.texto_de_la_tarea(tarea())}
    assert http.gets == 2 and f["estado"] == "respondida" and f["resultados"][0]["sql"] == SQL_OK
    assert (f["tokens_entrada"], f["tokens_salida"], f["tokens_cache_lectura"], f["costo_usd"]) == (16000, 1200, 0, 0.0242)
    assert f["fin"] > f["inicio"] and len(f["spans_herramientas"]) == 2


def test_sin_202_la_tarea_queda_como_error_del_api():
    class Rechaza(Http):
        def __call__(self, metodo, ruta, token, cuerpo):
            return 400, {"error": "pregunta_invalida"}

    f = medir_con(Rechaza())(tarea())
    assert f["estado"] == "error_api" and f["http"] == 400


def test_controles_de_acceso_esperan_401_sin_token_y_403_con_el_rol_equivocado():
    filas = E.controles_de_acceso(Http(), JWT)
    assert [(f["ruta"], f["esperado"], f["obtenido"], f["ok"]) for f in filas] == [
        ("/consultas", 401, 401, True), ("/aprobaciones/no-existe", 403, 403, True)]

    class Abierto(Http):
        def __call__(self, metodo, ruta, token, cuerpo):
            return 202, {}

    assert not any(f["ok"] for f in E.controles_de_acceso(Abierto(), JWT))


# ---------------------------------------------------------------- cold or warm

def test_frio_si_el_agente_corrio_su_init_en_la_ventana():
    a = E.arranque({"agente": [REPORTE_FRIO], "consultas": [REPORTE_CALIENTE, REPORTE_CALIENTE]})
    assert a["clase"] == "frio" and a["agente"]["init_ms"] == 1873.42 and a["consultas"]["frio"] is False


def test_caliente_sin_init_y_desconocido_sin_linea_report():
    assert E.arranque({"agente": [REPORTE_CALIENTE], "consultas": [REPORTE_FRIO]})["clase"] == "caliente"
    a = E.arranque({"agente": [], "consultas": [REPORTE_CALIENTE]})
    assert a["clase"] == "desconocido" and a["agente"] is None


def test_la_latencia_se_resume_aparte_en_frio_y_en_caliente():
    filas = [{"latencia_s": 30.0, "arranque": {"clase": "frio"}}, {"latencia_s": 20.0, "arranque": {"clase": "frio"}},
             *({"latencia_s": float(s), "arranque": {"clase": "caliente"}} for s in range(10, 30)),
             {"latencia_s": 99.0, "arranque": {"clase": "desconocido"}}]
    r = E.resumen_latencia(filas)
    assert r["frio"] == {"n": 2, "p50_s": 20.0, "p95_s": 30.0}
    assert r["caliente"]["n"] == 20 and r["caliente"]["p50_s"] == 19.0 and r["caliente"]["p95_s"] == 28.0
    assert r["desconocido"]["n"] == 1


# ---------------------------------------------------------------- trajectory graders

def test_la_trayectoria_sale_de_los_spans_y_la_califican_los_graders_de_la_semana_17():
    f = medir_con()(tarea())
    t = E.trayectoria_de_spans(f["spans_herramientas"], f["pasos"])
    assert [c.herramienta for c in t.llamadas] == ["describir_esquema", "ejecutar_sql"] and t.pasos == 3
    r = E.calificar_trayectoria("s03-es", f)
    assert r["ok"] is True and r["fallan"] == []


def test_demasiados_pasos_reprueban_la_trayectoria():
    f = {**medir_con()(tarea()), "pasos": 9}
    r = E.calificar_trayectoria("s03-es", f)
    assert r["ok"] is False and "pasos" in r["fallan"]


def test_una_tarea_no_corrida_no_se_califica():
    assert E.calificar_trayectoria("s03-es", {"estado": "no_corrida"}) is None


# ---------------------------------------------------------------- the run, its cap and the judge's context

def test_la_corrida_verifica_registra_el_contexto_y_clasifica_el_arranque():
    filas = E.correr([tarea()], medir=medir_con(), ejecutar_sql=ejecutar_ok,
                     reportes=lambda a, b: {"agente": [REPORTE_CALIENTE], "consultas": [REPORTE_CALIENTE]},
                     tope=C.Tope(usd=E.TOPE_USD, tokens=E.TOPE_TOKENS))
    (f,) = filas
    assert f["verificacion"]["exito"] is True and f["arranque"]["clase"] == "caliente" and f["trayectoria"]["ok"]
    assert f["contexto"] == [{"sql": SQL_OK, "filas": [["SKU-0009"]], "error": None}]


def test_el_tope_aborta_y_la_tarea_abortada_se_reporta_como_tal():
    lim = C.limite_de_tarea()
    tope = C.Tope(usd=lim.usd * 1.5, tokens=E.TOPE_TOKENS)
    medidas = []
    medir = medir_con()
    filas = E.correr([tarea("s03-es"), tarea("s06-es"), tarea("s03-en", "en")],
                     medir=lambda t: medidas.append(t["id"]) or {**medir(t), "costo_usd": lim.usd},
                     ejecutar_sql=ejecutar_ok, reportes=lambda a, b: {}, tope=tope)
    assert medidas == ["s03-es"]
    assert [(f["id_tarea"], f["estado"], f.get("motivo")) for f in filas[1:]] == [
        ("s06-es", "no_corrida", "tope_del_script"), ("s03-en", "no_corrida", "tope_del_script")]
    r = E.resumen_exito(filas)
    assert r["total"]["n"] == 3 and r["total"]["abortadas"] == 2 and r["total"]["exito"] == 1


def test_el_tope_cuenta_las_corridas_previas_y_la_repetida_se_conserva(tmp_path):
    (tmp_path / E.CRUDO).write_text(json.dumps({"gasto": {"usd": 0.5, "tokens": 200_000}}))
    assert E.descartar_previa(tmp_path).name == "crudo_eval_descartada_1.json"
    t = E.tope_con_lo_previo(tmp_path)
    assert (t.gastado_usd, t.gastado_tokens) == (0.5, 200_000)


def test_exito_con_intervalo_de_wilson_por_idioma_y_total():
    filas = [{"idioma": "es", "verificacion": {"exito": True}}] * 9 + [{"idioma": "es", "verificacion": {"exito": False}}] \
        + [{"idioma": "en", "verificacion": {"exito": True}}] * 10
    r = E.resumen_exito(filas)
    assert (r["es"]["exito"], r["en"]["exito"], r["total"]["tasa"]) == (9, 10, 0.95)
    assert r["total"]["ic95"][0] == round(E.wilson(19, 20)[0], 3) and r["en"]["ic95"][1] == 1.0


# ---------------------------------------------------------------- regression against the baselines

def test_la_linea_base_es_la_semana_17_local_sobre_las_mismas_20_tareas():
    s17 = E.linea_base_semana17()
    assert sorted(s17) == sorted(t["id"] for t in E.tareas_ci())
    s13 = E.semana13_por_tarea()
    assert all(i in s13 for i in s17)


def test_la_comparacion_aplica_la_regla_por_idioma_y_en_total():
    filas = [{"id_tarea": t["id"], "verificacion": {"exito": t["id"] != "c02-es"}} for t in E.tareas_ci()]
    r = E.comparar_con_lineas_base(filas, s17={t["id"]: True for t in E.tareas_ci()}, s13={}, a7={"s03-es": True})
    assert r["regla"]["es"] == {"base": 1.0, "valor": 0.9, "n": 10, "umbral": 0.9, "regresion": False}
    assert r["regla"]["total"]["umbral"] == 0.95 and r["regla"]["total"]["regresion"] is False and r["regresion"] is False
    assert r["actividad7"]["tareas_comunes"] == ["s03-es"]
    dos = [{**f, "verificacion": {"exito": f["id_tarea"] not in ("c02-es", "c06-es")}} for f in filas]
    r = E.comparar_con_lineas_base(dos, s17={t["id"]: True for t in E.tareas_ci()}, s13={}, a7={})
    assert r["regla"]["es"]["regresion"] is True and r["regla"]["total"]["regresion"] is True and r["regresion"] is True


# ---------------------------------------------------------------- outputs

def test_la_linea_de_detalle_tiene_el_esquema_documentado():
    f = E.correr([tarea()], medir=medir_con(), ejecutar_sql=ejecutar_ok,
                 reportes=lambda a, b: {"agente": [REPORTE_FRIO]}, tope=C.Tope(usd=1, tokens=10**6))[0]
    linea = E.linea_detalle(f, "principal", {"aprobado": True})
    assert tuple(linea) == E.CAMPOS_DETALLE
    assert linea["arranque"] == "frio" and linea["exito"] is True and linea["veredicto_juez"] == {"aprobado": True}


def test_ningun_token_ni_contrasena_en_lo_que_se_escribe(tmp_path, monkeypatch):
    f = E.correr([tarea()], medir=medir_con(Http(final={"id": "x", "estado": "respondida", "respuesta": f"token {JWT}",
                                                       "resultados": []})),
                 ejecutar_sql=ejecutar_ok, reportes=lambda a, b: {}, tope=C.Tope(usd=1, tokens=10**6))
    archivo = E.escribir("x.json", {"filas": f, "plan": E.plan(E.tareas_ci(), E.tareas_de_calentamiento())},
                         ["123456789012"], carpeta=tmp_path)
    texto = archivo.read_text()
    assert JWT not in texto and "<token>" in texto
    assert "PASSWORD" not in texto and "password" not in texto.lower()


def test_la_simulacion_no_crea_clientes_de_aws(monkeypatch, capsys):
    import boto3
    monkeypatch.setattr(boto3, "Session", lambda *a, **k: pytest.fail("la simulación no toca AWS"))
    assert E.main([]) == 0
    assert "Simulación" in capsys.readouterr().out


# ---------------------------------------------------------------- resultados/eval_aws_detalle.jsonl (week 20's baseline)

def _crudo_falso():
    comun = dict(medir=medir_con(), ejecutar_sql=ejecutar_ok,
                 reportes=lambda a, b: {"agente": [REPORTE_CALIENTE], "consultas": [REPORTE_CALIENTE]})
    tope = C.Tope(usd=E.TOPE_USD, tokens=E.TOPE_TOKENS)
    frio = E.correr([tarea("s01-es")], tope=tope, **comun)
    principal = E.correr([tarea("s03-es"), tarea("s03-en", "en")], tope=tope, **comun)
    principal.append({"id_tarea": "c02-es", "idioma": "es", "estado": "no_corrida", "motivo": "tope_del_script",
                      "estado_esperado": "respondida"})
    return {"calentamiento": frio, "filas": principal}


def test_el_detalle_cumple_el_esquema_y_se_escribe_una_linea_por_tarea(tmp_path):
    juez = {"por_tarea": {"s03-es": {"puntajes": {"Builtin.Correctness": 1.0, "Builtin.Faithfulness": 1.0}}}}
    lineas = E.detalle(_crudo_falso(), juez)
    assert [(l["id"], l["fase"]) for l in lineas] == [("s01-es", "calentamiento"), ("s03-es", "principal"),
                                                      ("s03-en", "principal"), ("c02-es", "principal")]
    assert all(E.validar_detalle(l) == [] for l in lineas)
    assert lineas[1]["veredicto_juez"]["aprobado"] is True and lineas[2]["veredicto_juez"] is None
    assert lineas[3]["estado"] == "no_corrida" and lineas[3]["exito"] is False and lineas[3]["arranque"] is None
    archivo = E.escribir_detalle(lineas, tmp_path / "eval_aws_detalle.jsonl")
    leidas = [json.loads(x) for x in archivo.read_text().splitlines()]
    assert leidas == lineas and all(tuple(l) == E.CAMPOS_DETALLE for l in leidas)


def test_una_linea_fuera_del_esquema_no_se_escribe(tmp_path):
    (l, *_) = E.detalle(_crudo_falso())
    assert E.validar_detalle({**l, "exito": 1}) == ["exito: int"]
    assert E.validar_detalle({**l, "arranque": "tibio"}) == ["arranque tibio"]
    assert E.validar_detalle({k: v for k, v in l.items() if k != "pasos"})
    with pytest.raises(ValueError, match="fuera del esquema"):
        E.escribir_detalle([{**l, "fase": "otra"}], tmp_path / "x.jsonl")
    assert not (tmp_path / "x.jsonl").exists()


def test_el_esquema_documenta_cada_campo():
    assert tuple(E.ESQUEMA_DETALLE) == E.CAMPOS_DETALLE and all(d for _, d in E.ESQUEMA_DETALLE.values())
