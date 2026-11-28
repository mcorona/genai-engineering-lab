"""Week 20, activity 4, R0: the local Haiku 4.5 baseline's script (request shape, run cap, budget, report), offline."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

S20 = Path(__file__).resolve().parents[1]


def _cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R0 = _cargar("ruteo_r0_local", S20 / "ruteo" / "r0_local.py")


def _respuesta(tin=1000, tout=100):
    return {"content": [{"type": "text", "text": "{}"}], "stop_reason": "end_turn",
            "usage": {"input_tokens": tin, "output_tokens": tout}}


def _converse(tin=1000, tout=100):
    return {"output": {"message": {"role": "assistant", "content": [{"text": "{}"}]}}, "stopReason": "end_turn",
            "usage": {"inputTokens": tin, "outputTokens": tout}}


CUERPO = {"model": "x", "max_tokens": 4000, "system": "prompt", "output_config": {"effort": "low"},
          "messages": [{"role": "user", "content": "¿cuántos?"}]}


def test_the_paid_run_sends_week_19s_converse_request_without_guardrail_or_cache_point():
    enviados = []
    api = R0.api_bedrock(lambda req: enviados.append(req) or _converse(), R0.Tope(usd=1.0, tokens=10**6, entrada_1m=1.1, salida_1m=5.5))
    resp = api(CUERPO)
    assert enviados == [{"modelId": R0.MODELO_ID, "system": [{"text": "prompt"}],
                         "messages": [{"role": "user", "content": [{"text": "¿cuántos?"}]}],
                         "inferenceConfig": {"maxTokens": 4000}}]
    assert resp["usage"]["input_tokens"] == 1000 and resp["stop_reason"] == "end_turn"


def test_the_model_is_the_deployed_agents_haiku_4_5_profile_from_ia_config():
    config = (S20.parent / "semana-19" / "ia" / "config.py").read_text(encoding="utf-8")
    assert R0.MODELO_ID == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert f'MODELO_ID = "{R0.MODELO_ID}"' in config


def test_the_run_cap_refuses_the_call_that_starts_past_it_and_never_reaches_the_api():
    llamadas = []
    tope = R0.Tope(usd=0.0066, tokens=10**6, entrada_1m=1.1, salida_1m=5.5)
    api = tope.envolver(lambda c: llamadas.append(c) or _respuesta(tin=1000, tout=1000))   # 0.0066 USD per call
    api({})
    assert tope.gastado == pytest.approx(0.0066)
    with pytest.raises(R0.TopeAlcanzado):
        api({})
    assert len(llamadas) == 1


def test_the_token_cap_refuses_the_call_that_starts_past_it():
    llamadas = []
    tope = R0.Tope(usd=100.0, tokens=2000, entrada_1m=1.1, salida_1m=5.5)
    api = tope.envolver(lambda c: llamadas.append(c) or _respuesta(tin=1500, tout=500))
    api({})
    assert tope.tokens_gastados == 2000
    with pytest.raises(R0.TopeAlcanzado):
        api({})
    assert len(llamadas) == 1


def test_the_cap_counts_every_call_while_under_it():
    tope = R0.Tope(usd=1.0, tokens=10**6, entrada_1m=1.1, salida_1m=5.5)
    api = tope.envolver(lambda c: _respuesta(tin=10_000, tout=1_000))
    for _ in range(3):
        api({})
    assert tope.gastado == pytest.approx(3 * (0.011 + 0.0055))
    assert (tope.llamadas, tope.tokens_gastados) == (3, 33_000)


def test_the_prices_are_the_price_lists_regional_haiku_4_5_skus():
    t = R0.tope_de_haiku45(1.5, 1_000_000)
    assert (t.entrada_1m, t.salida_1m) == (1.1, 5.5)
    assert R0.SKUS == {"entrada": "JQDUC8Q4K8C6GSGH", "salida": "X629GDA2GXAP6R54"}


def test_the_task_budget_prices_haiku_4_5_at_the_same_price_as_the_run_cap():
    sys_path = str(S20.parent / "semana-17")
    import sys
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from presupuestos.estimacion import precio
    t = R0.tope_de_haiku45(1.5, 1_000_000)
    assert precio(R0.MODELO_PRESUPUESTO) == (t.entrada_1m, t.salida_1m)


def test_the_task_budget_is_the_deployed_ceiling_of_week_20():
    p = R0.politica()
    assert (p.tarea.usd, p.tarea.tokens) == (0.12, 100_000)
    assert p.sesion is None and p.tenant_dia is None


def _fila(i, exito, estado="respondida"):
    return {"id": i, "exito": exito, "estado": estado}


IDS = [f"{t}-{l}" for l in ("es", "en") for t in ("s03", "s06", "r02", "r05", "r12", "c02", "c06", "v01", "a01", "n01")]


def _aws(fallan, estados=None):
    estados = estados or {}
    return {i: {"exito": i not in fallan, "estado": estados.get(i, "respondida" if i not in fallan else "abstenida")}
            for i in IDS}


DESPLEGADA = ("c02-es", "c02-en", "r05-es", "r05-en")
CACHE = ("c02-es", "c06-en", "r05-en")


def test_the_report_puts_r0_beside_week_17_the_deployed_run_and_the_cache_run_per_task():
    r0 = [_fila(i, i not in ("c02-es", "c02-en")) for i in IDS]
    inf = R0.comparar(r0, s17={i: True for i in IDS}, desplegada=_aws(DESPLEGADA), cache=_aws(CACHE))
    assert inf["exito"] == {"es": "9/10", "en": "9/10", "total": "18/20"}
    assert inf["fallan"] == {"r0": ["c02-en", "c02-es"], "desplegada": ["c02-en", "c02-es", "r05-en", "r05-es"],
                             "cache": ["c02-es", "c06-en", "r05-en"]}
    assert inf["por_tarea"]["r05-es"] == {"r0": True, "semana17": True, "desplegada": False, "cache": True}


def test_the_silently_wrong_answers_are_answered_tasks_the_verifier_rejects():
    r0 = [_fila(i, i != "c06-en") for i in IDS[:-1]] + [_fila(IDS[-1], False, estado="abstenida")]
    inf = R0.comparar(r0, s17={i: True for i in IDS}, desplegada=_aws(DESPLEGADA),
                      cache=_aws(CACHE, {"c02-es": "requiere_aclaracion", "c06-en": "respondida", "r05-en": "limite_alcanzado"}))
    assert inf["silenciosamente_equivocadas"] == {"r0": ["c06-en"], "desplegada": [], "cache": ["c06-en"]}


def test_failures_only_r0_has_are_the_models_and_only_the_deployed_runs_have_are_the_ports():
    r0 = [_fila(i, i not in ("c02-es", "c02-en")) for i in IDS]
    c = R0.comparar(r0, s17={i: True for i in IDS}, desplegada=_aws(DESPLEGADA), cache=_aws(CACHE))["conclusion"]
    assert c["efecto_modelo"] == ["c02-en", "c02-es"]
    assert c["efecto_port"] == ["c06-en", "r05-en", "r05-es"]


def test_r0_without_regression_puts_the_gap_on_the_port_and_r1_is_measured_against_the_cache_run_only():
    c = R0.comparar([_fila(i, True) for i in IDS], s17={i: True for i in IDS}, desplegada=_aws(DESPLEGADA),
                    cache=_aws(CACHE))["conclusion"]
    assert c["causa"] == "port"
    assert c["linea_base_r1"] == {"veredicto_contra": "cache", "tambien_contra_semana17": False}


def test_r0_with_regression_puts_the_gap_on_the_model_and_r1_is_also_measured_against_week_17():
    r0 = [_fila(i, i not in DESPLEGADA) for i in IDS]
    c = R0.comparar(r0, s17={i: True for i in IDS}, desplegada=_aws(DESPLEGADA), cache=_aws(DESPLEGADA))["conclusion"]
    assert c["causa"] == "modelo" and c["efecto_port"] == []
    assert c["linea_base_r1"] == {"veredicto_contra": "cache", "tambien_contra_semana17": True}
    mixta = R0.comparar(r0, s17={i: True for i in IDS}, desplegada=_aws(DESPLEGADA), cache=_aws(CACHE))["conclusion"]
    assert mixta["causa"] == "ambos"


def test_the_week_10_rule_is_against_week_17s_local_20_of_20():
    r0 = [_fila(i, i not in DESPLEGADA) for i in IDS]
    inf = R0.comparar(r0, s17={i: True for i in IDS}, desplegada=_aws(()), cache=_aws(()))
    assert inf["regla_semana10"]["total"]["base"] == 1.0
    assert inf["regla_semana10"]["total"]["regresion"] is True
    perfecto = R0.comparar([_fila(i, True) for i in IDS], s17={i: True for i in IDS}, desplegada=_aws(()), cache=_aws(()))
    assert perfecto["regresion"] is False


def test_the_aws_runs_are_read_from_their_main_tasks_only():
    d = R0.corrida_aws(S20 / "resultados" / "corrida_corregida_detalle.jsonl")
    c = R0.corrida_aws(S20 / "resultados" / "cache_detalle.jsonl")
    assert sorted(d) == sorted(c) == sorted(IDS)
    assert [i for i, f in sorted(d.items()) if not f["exito"]] == ["c02-en", "c02-es", "r05-en", "r05-es"]
    assert [(i, f["estado"]) for i, f in sorted(c.items()) if not f["exito"]] == [
        ("c02-es", "requiere_aclaracion"), ("c06-en", "respondida"), ("r05-en", "limite_alcanzado")]


def test_week_17s_baseline_is_its_local_ci_file():
    s17 = R0.semana17()
    assert sorted(s17) == sorted(IDS) and all(s17.values())


def test_a_task_the_cap_stopped_is_not_run_and_counts_as_a_failure(tmp_path):
    r0 = [_fila(i, True) for i in IDS[:-1]] + [{"id": IDS[-1], "exito": False, "estado": "error",
                                                 "motivo": "api: tope de la corrida"}]
    inf = R0.comparar(r0, s17={i: True for i in IDS}, desplegada=_aws(()), cache=_aws(()))
    assert inf["no_corridas"] == [IDS[-1]]
    assert inf["exito"]["total"] == "19/20"


def test_a_paid_run_needs_an_aws_profile_and_the_database_never_an_anthropic_key():
    assert R0.faltantes({}, si=True) == ["AWS_PROFILE", "PG_ADMIN_DSN"]
    assert R0.faltantes({"ANTHROPIC_API_KEY": "x", "PG_ADMIN_DSN": "y"}, si=True) == ["AWS_PROFILE"]
    assert R0.faltantes({"PG_ADMIN_DSN": "x"}, si=False) == []
    assert R0.faltantes({}, si=False) == ["PG_ADMIN_DSN"]


def test_the_raw_file_has_ids_and_numbers_only(tmp_path):
    sub = {"filas": [{"id": "s03-es", "corrida": "abc", "estado": "respondida", "motivo": None, "exito": True,
                      "usd": 0.01, "tope_usd": 0.12, "sobre_el_tope": False, "trayectoria_ok": True, "fallan": []}],
           "presupuesto": {"tarea": "s03-es", "estado": "limite_alcanzado"}, "omisiones_del_esquema": {}}
    salida = R0.crudo(sub, tope=R0.Tope(usd=1.5, tokens=10**6, entrada_1m=1.1, salida_1m=5.5), modo="simulacion", segundos=1.0)
    assert salida["modelo"] == R0.MODELO_ID and salida["tope_tokens"] == 10**6 and salida["modo"] == "simulacion" and salida["tope_usd"] == 1.5
    assert set(salida["filas"][0]) <= R0.CAMPOS_FILA
    assert "respuesta" not in json.dumps(salida)
