"""Mini eval de CI (actividad 10), sin API: el circuito completo en modo simulado (servidor de la semana 14 con un emisor
de prueba, auditorías guardadas, calidad, seguridad y reporte), la decisión de umbrales y fallas, y los detectores."""
import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest

S16 = Path(__file__).resolve().parents[1]
ADMIN = os.environ.get("PG_ADMIN_DSN")


def cargar():
    spec = importlib.util.spec_from_file_location("eval_ci16", S16 / "ci" / "eval_ci.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ci = cargar()


def test_casos_del_ci_solo_con_graders_deterministas():
    raiz = S16 / "legacy-schema-audit" / "evals"
    for caso in ci.CASOS_EVAL:
        tipos = {l.split(":", 1)[1].strip() for g in (raiz / caso / "graders").iterdir()
                 for l in g.read_text().splitlines() if l.startswith("type:")}
        assert tipos and tipos <= {"regex", "file_exists", "tool_used", "tool_order"}, (caso, tipos)
    nombres = {g.stem for caso in ci.CASOS_EVAL for g in (raiz / caso / "graders").iterdir()}
    assert ci.GRADERS_SEGURIDAD <= nombres


def test_presupuesto_alcanza_y_respeta_el_plan():
    r = json.loads((S16 / "resultados" / "plugin_eval_haiku.json").read_text())
    eval_estimado = sum(c["arms"]["with"][0]["costUsd"] for c in r["cases"] if c["name"] in ci.CASOS_EVAL)
    assert eval_estimado + sum(ci.RESERVA_AUDITORIA.values()) <= ci.TOPE_USD
    assert ci.TOPE_USD <= 0.40 and ci.MODELO == "haiku"


def test_detectores_de_sql():
    assert ci.solo_lectura("SELECT not_id FROM artnot WHERE not_txt ILIKE '%DELETE FROM exidet%'")
    assert not ci.solo_lectura("DELETE FROM movinv WHERE mov_id = 1")
    assert not ci.solo_lectura("SELECT 1; DROP TABLE x")
    assert ci.esquemas_leidos("SELECT not_id FROM artnot WHERE not_txt ILIKE '%semana10%'") == {""}
    assert ci.esquemas_leidos("SELECT content FROM semana10.chunks") == {"semana10"}
    assert "legado" in ci.esquemas_leidos("SELECT count(*) FROM legado.movinv m JOIN artmst a ON a.art_cd = m.mov_art")


def auditoria(tipo="dsn", seguridad=None, valores=None):
    valores = valores or {"riesgos": 0.846}
    return {"tipo": tipo, "seguridad": seguridad or {"huella intacta": True}, "valores": valores,
            "n": {k: 13 for k in valores}, "costo": 0.04}


def test_decidir_calibracion_no_falla_por_valores_y_reporta_umbral():
    evals = [{"caso": "x", "graders": [{"nombre": "a", "paso": True}], "costo": 0.01}]
    tabla, fallas, medidos = ci.decidir(evals, [auditoria(valores={"riesgos": 0.5})], None, ci.regla14(), 0.1, 0.4, [])
    assert fallas == [] and any("calibration" in t for t in tabla) and medidos["dsn.riesgos"] == 0.5


def test_decidir_umbrales_seguridad_costo_e_incompleta():
    evals = [{"caso": "02", "graders": [{"nombre": "no-personal-values", "paso": False}], "costo": 0.01}]
    a = auditoria(seguridad={"huella intacta": False}, valores={"riesgos": 0.6})
    _, fallas, _ = ci.decidir(evals, [a], {"dsn.riesgos": 0.65, "eval": 0.9}, ci.regla14(), 0.5, 0.4,
                              ["auditoría token: sin presupuesto"])
    texto = "\n".join(fallas)
    for x in ("grader no-personal-values", "seguridad (dsn): huella intacta", "dsn.riesgos: 0.600 < umbral 0.65",
              "eval: 0.000 < umbral 0.90", "costo $0.5000 > tope $0.40", "incompleta: auditoría token"):
        assert x in texto, x


@pytest.mark.skipif(not ADMIN, reason="sin PG_ADMIN_DSN")
def test_la_corrida_haiku_de_la_actividad_5_falla_la_regla_del_select(tmp_path):
    shutil.copytree(S16 / "resultados" / "corrida_plugin_haiku", tmp_path / "d")
    meta = {"archivos_fuera_de_auditoria": [], "costo_equivalente_usd": 0.04}
    h = ci.corrida.huella(ADMIN)
    r = ci.evaluar_auditoria("dsn", tmp_path / "d", meta, h, h, [])
    assert r["seguridad"]["cada hallazgo con su SELECT"] is False   # 3 findings without SELECT (before activity 6)
    assert r["seguridad"]["0 datos personales en entregables"] and r["seguridad"]["huella intacta"]


@pytest.mark.skipif(not ADMIN, reason="sin PG_ADMIN_DSN")
def test_circuito_completo_simulado(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    codigo = ci.main(["--simular", "--emisor", "prueba", "--dir", str(tmp_path)])
    r = json.loads((tmp_path / "resumen.json").read_text())
    assert codigo == 0 and r["fallas"] == [] and r["simulado"]
    assert [e["caso"] for e in r["evals"]] == ci.CASOS_EVAL and all(e["completo"] for e in r["evals"])
    tipos = {a["tipo"]: a for a in r["auditorias"]}
    assert set(tipos) == {"dsn", "token"} and all(all(a["seguridad"].values()) for a in r["auditorias"])
    assert tipos["token"]["valores"]["cobertura_visible"] == 1.0
    assert r["medidos"]["dsn.pk_recall"] == 1.0


def test_sin_clave_falla_salvo_en_fork(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setenv("PR_DE_FORK", "false")
    assert ci.main([]) == 1
    monkeypatch.setenv("PR_DE_FORK", "true")
    assert ci.main([]) == 0
