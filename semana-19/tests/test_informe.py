"""Week 19, activity 8: the report's data block is rendered from the run's files, never typed by hand."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19 / "tests"))


def _cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


I = _cargar("informe", S19 / "eval" / "informe.py")
TE = _cargar("prueba_eval_aws", S19 / "tests" / "test_eval_aws.py")       # its fakes: Http, spans, tarea
TA = _cargar("prueba_aprobacion", S19 / "tests" / "test_aprobacion_e2e.py")
CJ = _cargar("cj", S19 / "eval" / "comparar_jueces.py")
E, C = TE.E, TE.C


def crudo():
    tope = C.Tope(usd=E.TOPE_USD, tokens=E.TOPE_TOKENS)
    comun = dict(medir=TE.medir_con(), ejecutar_sql=TE.ejecutar_ok, tope=tope)
    frio = E.correr([TE.tarea("s01-es")], reportes=lambda a, b: {"agente": [TE.REPORTE_FRIO]}, **comun)
    filas = E.correr([TE.tarea(t["id"], t["idioma"]) for t in E.tareas_ci()],
                     reportes=lambda a, b: {"agente": [TE.REPORTE_CALIENTE]}, **comun)
    filas[-1] = {"id_tarea": filas[-1]["id_tarea"], "idioma": filas[-1]["idioma"], "estado": "no_corrida",
                 "motivo": "tope_del_script", "estado_esperado": "respondida"}
    acceso = E.controles_de_acceso(TE.Http(), TE.JWT)
    return {"fecha": "2026-11-19", "acceso": acceso, "calentamiento": frio, "filas": filas,
            "gasto": E.gasto(frio + filas), "tope": {"usd": E.TOPE_USD, "tokens": E.TOPE_TOKENS},
            "resumen": {"exito": E.resumen_exito(filas), "latencia": E.resumen_latencia(frio + filas),
                        "trayectoria": E.resumen_trayectoria(filas), "costo": E.resumen_costo(frio + filas),
                        "comparacion": E.comparar_con_lineas_base(filas)}}


def aprobacion():
    r = TA.correr(TA.AwsFalso())
    return {**r, "gasto": {"usd": 0.04, "tokens": 31800}, "tope": {"usd": 0.2, "tokens": 100000}}


def juez_y_comparacion():
    casos = __import__("test_comparar_jueces").caso()
    juez = {"trabajo": "semana19-juez-x", "estado": "Completed", "duracion_s": 900, "juez": "us.amazon.nova-pro-v1:0",
            "estimacion": {"usd": 0.16, "tope_usd": 0.45}, "por_tarea": {c["id"]: c for c in casos}}
    return juez, CJ.comparar(casos)


def test_sin_archivos_dice_que_no_corrio_y_no_pone_cifras():
    texto = I.render(None)
    assert texto.startswith(I.INICIO) and texto.rstrip().endswith(I.FIN)
    assert "crudo_eval.json does not exist" in texto and "aprobacion_e2e.json does not exist" in texto
    assert "juez_bedrock.json does not exist" in texto and "Schema of eval_aws_detalle.jsonl" in texto


def test_las_cifras_del_bloque_son_las_del_archivo():
    c = crudo()
    texto = I.render(c, aprobacion(), *juez_y_comparacion())
    e = c["resumen"]["exito"]["total"]
    assert f"| total | {e['n']} | {e['exito']} | {I._n(e['tasa'])} | [{I._n(e['ic95'][0])}, {I._n(e['ic95'][1])}] | 1 |" in texto
    assert f"Tasks aborted by the cap: {c['filas'][-1]['id_tarea']}." in texto
    regla = c["resumen"]["comparacion"]["regla"]["total"]
    assert f"| total | 20 | {I._n(regla['base'])} | {I._n(regla['valor'])} | {I._n(regla['umbral'])} |" in texto
    assert "| cold | 1 |" in texto and "| warm | 19 |" in texto
    assert "| 0.0242 |" in texto        # the cost per task keeps its decimals
    assert "Agreement 0.8, Cohen's kappa 0.5833 (n = 10" in texto and "| Verifier fails | 1 | 3 |" in texto
    assert "All five checks passed: yes" in texto and "| 5 | una solicitud vencida no escribe | yes |" in texto
    assert all(f"| {k} |" in texto for k in E.CAMPOS_DETALLE)


def test_el_bloque_se_reemplaza_y_el_analisis_a_mano_se_queda():
    previo = "# Title\n\nHand-written analysis.\n\n" + I.render(None) + "\n## Decision\n\nKept.\n"
    nuevo = I.con_bloque(previo, I.render(crudo()))
    assert nuevo.startswith("# Title\n\nHand-written analysis.") and nuevo.endswith("## Decision\n\nKept.\n")
    assert nuevo.count(I.INICIO) == 1 and "crudo_eval.json does not exist" not in nuevo
    assert I.con_bloque("", I.render(None)) == I.render(None)


def test_el_bloque_no_trae_tokens_ni_cuentas():
    texto = I.render(crudo(), aprobacion(), *juez_y_comparacion())
    assert TE.JWT not in texto and TA.TOKEN_TAREA not in texto
    assert not any(s in texto for s in TA.SUBS.values())


def test_las_corridas_descartadas_salen_con_su_gasto_y_sus_herramientas():
    c = crudo()
    n_sql = sum(sp["gen_ai.tool.name"] == "ejecutar_sql" for f in c["filas"] for sp in f.get("spans_herramientas") or [])
    texto = I.render(crudo(), descartadas=[("crudo_eval_descartada_1.json", c)])
    e = c["resumen"]["exito"]["total"]
    assert f"| crudo_eval_descartada_1.json | 2026-11-19 | {e['exito']}/{e['n']} |" in texto
    assert f"| {I._n(c['gasto']['usd'], 6)} | {c['gasto']['tokens']:,} |" in texto and f"ejecutar_sql {n_sql} |" in texto
    assert "### Discarded runs (kept; their spend counts)\n\nNone." in I.render(crudo())
