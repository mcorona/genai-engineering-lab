"""Week 19, activity 8: the judge's dataset, cap, request and results, offline."""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))
spec = importlib.util.spec_from_file_location("juez_bedrock", S19 / "eval" / "juez_bedrock.py")
J = importlib.util.module_from_spec(spec)
spec.loader.exec_module(J)
spec = importlib.util.spec_from_file_location("eval_aws_para_prueba_juez", S19 / "eval" / "eval_aws.py")
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)

# The documented example line (model-evaluation-prompt-datasets-judge.html), its keys only.
EJEMPLO_DOCUMENTADO = {"prompt": "What is high intensity interval training?", "referenceResponse": "HIIT is ...",
                       "category": "Fitness", "modelResponses": [{"response": "HIIT is ...", "modelIdentifier": "my_model"}]}
JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJhYmMifQ.c2lnbmF0dXJh"


def crudo(n_abortadas=0):
    tareas = E.tareas_ci()
    filas, esperados = [], {}
    for i, t in enumerate(tareas):
        for clave in t["salida"]:
            esperados[f"{t['id']}/{clave}"] = [["SKU-0009", 12]]
        if i >= len(tareas) - n_abortadas:
            filas.append({"id_tarea": t["id"], "estado": "no_corrida", "motivo": "tope_del_script"})
            continue
        filas.append({"id_tarea": t["id"], "estado": "respondida", "respuesta": f"Son 12 piezas. {JWT}",
                      "contexto": [{"sql": "SELECT 1", "filas": [["SKU-0009", 12]], "error": None},
                                   {"sql": "SELECT x", "filas": [], "error": "columna inexistente"}]})
    return {"filas": filas, "esperados": esperados}


def test_las_lineas_tienen_el_esquema_documentado():
    lineas = J.construir(E.tareas_ci(), crudo(), ["123456789012"])
    assert len(lineas) == 20 and J.validar(lineas) == []
    assert all(set(l) == set(EJEMPLO_DOCUMENTADO) for l in lineas)
    assert all(set(l["modelResponses"][0]) == set(EJEMPLO_DOCUMENTADO["modelResponses"][0]) for l in lineas)
    assert {l["modelResponses"][0]["modelIdentifier"] for l in lineas} == {J.ID_RESPUESTAS}
    assert sorted(l["category"] for l in lineas) == sorted(t["id"] for t in E.tareas_ci())
    assert J.validar([EJEMPLO_DOCUMENTADO]) == []


def test_el_prompt_lleva_la_tarea_y_lo_que_devolvieron_las_herramientas():
    (l, *_) = J.construir(E.tareas_ci(), crudo())
    t = next(t for t in E.tareas_ci() if t["id"] == l["category"])
    assert l["prompt"].startswith(E.C.texto_de_la_tarea(t))
    assert '[1] filas: [["SKU-0009", 12]]' in l["prompt"] and "[2] error: columna inexistente" in l["prompt"]
    assert all(k.split("/")[1] in l["referenceResponse"] for k in crudo()["esperados"] if k.startswith(l["category"] + "/"))


def test_las_tareas_abortadas_no_se_juzgan_y_nada_sale_sin_redactar():
    lineas = J.construir(E.tareas_ci(), crudo(n_abortadas=3))
    assert len(lineas) == 17
    texto = J.jsonl(lineas)
    assert JWT not in texto and len(texto.splitlines()) == 17
    assert all(json.loads(x) for x in texto.splitlines())


def test_validar_rechaza_lo_que_el_trabajo_no_acepta():
    malo = [{**EJEMPLO_DOCUMENTADO, "contexto": "x"},
            {**EJEMPLO_DOCUMENTADO, "category": "b", "modelResponses": [{"response": "a", "modelIdentifier": "m"}] * 2},
            {**EJEMPLO_DOCUMENTADO, "category": "c", "modelResponses": [{"response": "a", "modelIdentifier": "otro"}]},
            {**EJEMPLO_DOCUMENTADO, "category": "c"}]
    errores = " | ".join(J.validar(malo))
    assert "claves" in errores and "una sola respuesta" in errores and "un solo modelIdentifier" in errores
    assert "category repetida" in errores
    assert J.validar([]) and J.validar([EJEMPLO_DOCUMENTADO] * 1001)


def test_el_prompt_largo_se_recorta():
    t = E.tareas_ci()[0]
    p = J.prompt_de(t, [{"sql": "SELECT 1", "filas": [["x" * 100]] * 200, "error": None}])
    assert len(p) <= J.LARGO_PROMPT and p.endswith("[recortado]")


def test_el_tope_se_estima_antes_de_crear_el_trabajo():
    est = J.estimar(J.construir(E.tareas_ci(), crudo()))
    assert est["cabe"] and 0 < est["usd"] <= J.TOPE_USD and est["tope_usd"] == 0.45
    grandes = [{**EJEMPLO_DOCUMENTADO, "prompt": "x" * 4_000_000}]
    assert J.estimar(grandes)["cabe"] is False


def test_la_solicitud_pasa_la_validacion_de_botocore_y_sus_patrones():
    import botocore.session
    from botocore.validate import ParamValidator
    modelo = botocore.session.get_session().get_service_model("bedrock")
    op = modelo.operation_model("CreateEvaluationJob")
    nombre = J.nombre_del_trabajo(1_795_000_000)
    p = J.solicitud(nombre, rol="arn:aws:iam::123456789012:role/semana19-eval-juez",
                    llave="arn:aws:kms:us-east-1:123456789012:key/abc", bucket="semana19-eval-juez")
    reporte = ParamValidator().validate(p, op.input_shape)
    assert not reporte.has_errors(), reporte.generate_report()
    patron = lambda forma: re.fullmatch(modelo.shape_for(forma).metadata["pattern"], {  # noqa: E731
        "EvaluationJobName": nombre, "EvaluationPrecomputedInferenceSourceIdentifier": J.ID_RESPUESTAS}[forma])
    assert patron("EvaluationJobName") and patron("EvaluationPrecomputedInferenceSourceIdentifier")
    assert re.search(modelo.shape_for("EvaluatorModelIdentifier").metadata["pattern"], J.MODELO_JUEZ)
    assert J.TIPO_DE_TAREA in modelo.shape_for("EvaluationTaskType").enum
    assert all(re.fullmatch(modelo.shape_for("EvaluationMetricName").metadata["pattern"], m) for m in J.METRICAS)
    assert {"key": "proyecto", "value": "semana19"} in p["jobTags"]


def test_el_juez_no_es_el_modelo_evaluado():
    from ia.config import MODELO_ID
    assert "nova" in J.MODELO_JUEZ and "anthropic" in MODELO_ID and J.MODELO_JUEZ != MODELO_ID


def registro(id_, correcto=1.0, fiel=1.0):
    return {"inputRecord": {"prompt": "p", "category": id_, "modelResponses": [{"response": "r", "modelIdentifier": "m"}]},
            "automatedEvaluationResult": {"scores": [
                {"metricName": "Builtin.Correctness", "result": correcto, "evaluatorDetails": [{"explanation": "ok"}]},
                {"metricName": "Faithfulness", "result": fiel}, {"metricName": "Builtin.Completeness", "result": None}]}}


def test_los_resultados_se_emparejan_por_category():
    r = J.leer_resultados([registro("s03-es"), registro("s03-en", 0.5)])
    assert r["s03-es"]["puntajes"] == {"Builtin.Correctness": 1.0, "Builtin.Faithfulness": 1.0, "Builtin.Completeness": None}
    assert r["s03-en"]["puntajes"]["Builtin.Correctness"] == 0.5 and r["s03-es"]["explicacion"] == "Builtin.Correctness: ok"


def test_un_formato_inesperado_falla_en_voz_alta():
    with pytest.raises(ValueError, match="category"):
        J.leer_resultados([{"automatedEvaluationResult": {}}])
    with pytest.raises(ValueError, match="fuera de"):
        J.leer_resultados([registro("x", correcto=3)])
    with pytest.raises(ValueError, match="dos registros"):
        J.leer_resultados([registro("x"), registro("x")])


def test_sin_corrida_la_simulacion_no_toca_aws(monkeypatch, capsys, tmp_path):
    import boto3
    monkeypatch.setattr(boto3, "Session", lambda *a, **k: pytest.fail("la simulación no toca AWS"))
    monkeypatch.setattr(J, "SALIDA", tmp_path)
    assert J.main([]) == 0 and "Simulación" in capsys.readouterr().out


def test_las_tareas_sin_filas_llevan_la_conducta_esperada_como_referencia():
    lineas = {l["category"]: l for l in J.construir(E.tareas_ci(), crudo())}
    assert lineas["a01-es"]["referenceResponse"].startswith("La respuesta correcta pide una aclaración")
    assert lineas["n01-en"]["referenceResponse"].startswith("La respuesta correcta se abstiene")
    t = next(t for t in E.tareas_ci() if t["id"] == "s03-es")
    with pytest.raises(ValueError, match="faltan"):
        J.referencia_de(t, {})
