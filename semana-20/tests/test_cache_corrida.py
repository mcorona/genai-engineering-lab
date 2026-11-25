"""Week 20, activity 3, step 4: the cache run's script (caps, required environment, per-step columns), without AWS."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

S20 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S20.parent / "semana-19"))


def _cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


CORR = _cargar("cache_corrida", S20 / "cache" / "corrida.py")


@pytest.fixture(scope="module")
def LB():
    return CORR.linea_base()


def test_el_tope_cuenta_solo_sus_propios_archivos(LB, tmp_path):
    E = LB._eval_aws()
    (tmp_path / "crudo_eval_descartada_1.json").write_text(json.dumps({"gasto": {"usd": 0.3, "tokens": 50_000}}))
    (tmp_path / "otra.json").write_text(json.dumps({"gasto": {"usd": 9.0, "tokens": 9}}))
    c = CORR.corrida(LB)
    t = LB.tope(E, tmp_path, c)
    assert (t.usd, t.gastado_usd, t.gastado_tokens) == (1.50, 0.3, 50_000)


@pytest.mark.parametrize("variables", [{"PRESUPUESTO_TAREA": "techo_semana20"},
                                       {"PRESUPUESTO_TAREA": "techo_semana20", "CACHE_PROMPT": "off"},
                                       {"CACHE_PROMPT": "historial"}])
def test_sin_la_cache_desplegada_no_se_manda_nada(LB, variables):
    with pytest.raises(SystemExit):
        LB.exigir_entorno(variables, CORR.corrida(LB))
    LB.exigir_entorno({"PRESUPUESTO_TAREA": "techo_semana20", "CACHE_PROMPT": "historial"}, CORR.corrida(LB))


def test_el_ttl_de_la_cache_es_el_de_omision(LB):
    entorno = {"PRESUPUESTO_TAREA": "techo_semana20", "CACHE_PROMPT": "historial"}
    with pytest.raises(SystemExit, match="CACHE_TTL=1h"):
        LB.exigir_entorno({**entorno, "CACHE_TTL": "1h"}, CORR.corrida(LB))
    LB.exigir_entorno(entorno, CORR.corrida(LB))


def test_la_corrida_corregida_sigue_igual(LB):
    assert LB.CORREGIDA.exigir == {"PRESUPUESTO_TAREA": "techo_semana20"} and LB.CORREGIDA.tope_usd == 2.50
    LB.exigir_entorno({"PRESUPUESTO_TAREA": "techo_semana20"})


def _paquete(archivos: dict[str, bytes]) -> bytes:
    """A deployment zip with the agent package's layout (app/agente/...)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("app/__init__.py", "")
        for nombre, contenido in archivos.items():
            z.writestr("app/" + nombre, contenido)
    return buf.getvalue()


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "agente").mkdir()
    archivos = {a: f"# {a}\nCACHE = True\n".encode() for a in CORR.CODIGO_CACHE}
    for a, contenido in archivos.items():
        (tmp_path / a).write_bytes(contenido)
    return tmp_path, archivos


def test_el_codigo_desplegado_igual_al_repositorio_pasa(LB, repo):
    raiz, archivos = repo
    assert LB.codigo_desplegado_al_dia(_paquete(archivos), raiz, CORR.CODIGO_CACHE) == []
    LB.exigir_codigo(_paquete(archivos), CORR.corrida(LB), raiz)


def test_un_archivo_cambiado_o_ausente_detiene_la_corrida(LB, repo):
    raiz, archivos = repo
    viejo = {**archivos, "agente/converse_adaptador.py": b"# before the cache\n"}
    assert LB.codigo_desplegado_al_dia(_paquete(viejo), raiz, CORR.CODIGO_CACHE) == ["agente/converse_adaptador.py"]
    sin = {a: c for a, c in archivos.items() if a != "agente/presupuesto.py"}
    assert LB.codigo_desplegado_al_dia(_paquete(sin), raiz, CORR.CODIGO_CACHE) == ["agente/presupuesto.py"]
    with pytest.raises(SystemExit, match="agente/converse_adaptador.py.*no task is sent"):
        LB.exigir_codigo(_paquete(viejo), CORR.corrida(LB), raiz)


def test_solo_la_corrida_con_cache_revisa_el_codigo(LB):
    assert LB.CORREGIDA.codigo_al_dia == ()
    LB.exigir_codigo(b"", LB.CORREGIDA)   # no files to check: the zip is not even opened
    c = CORR.corrida(LB)
    assert c.codigo_al_dia == CORR.CODIGO_CACHE and "agente/converse_adaptador.py" in c.codigo_al_dia
    assert all((LB.S19 / a).is_file() for a in c.codigo_al_dia)


def test_el_tope_del_script_cuenta_los_tokens_de_cache(LB):
    E = LB._eval_aws()
    assert E.tokens_de({"tokens_entrada": 10, "tokens_salida": 5, "tokens_cache_lectura": 100,
                        "tokens_cache_escritura": 20}) == 135
    assert E.tokens_de({"tokens_entrada": 10, "tokens_salida": 5}) == 15


FILA = {"id_tarea": "s03-es", "pasos": 3, "spans_completos": True, "duracion_pasos_ms": [900.0, 600.0, 500.0], "spans_modelo": [
    {"lab.step": 2, "gen_ai.usage.input_tokens": 40, "gen_ai.usage.output_tokens": 30,
     "gen_ai.usage.cache_read.input_tokens": 0, "gen_ai.usage.cache_creation.input_tokens": 4300, "lab.cost.usd": 0.006},
    {"lab.step": 1, "gen_ai.usage.input_tokens": 2900, "gen_ai.usage.output_tokens": 80,
     "gen_ai.usage.cache_read.input_tokens": 0, "gen_ai.usage.cache_creation.input_tokens": 0, "lab.cost.usd": 0.0036},
    {"lab.step": 3, "gen_ai.usage.input_tokens": 30, "gen_ai.usage.output_tokens": 200,
     "gen_ai.usage.cache_read.input_tokens": 4300, "gen_ai.usage.cache_creation.input_tokens": 400, "lab.cost.usd": 0.002}]}


def test_columnas_por_paso_y_aciertos():
    pasos = CORR.pasos_de(FILA)
    assert [p["paso"] for p in pasos] == [1, 2, 3] and [p["ms"] for p in pasos] == [900.0, 600.0, 500.0]
    assert CORR.aciertos(pasos) == {"posibles": 1, "leyeron": 1, "tasa": 1.0}
    (l,) = CORR.columnas({"filas": [FILA]}, [{"id": "s03-es", "fase": "principal"}])
    assert l["latencia_primer_paso_ms"] == 900.0 and l["latencia_pasos_siguientes_ms_mediana"] == 550.0
    assert l["region"] is None and len(l["pasos_modelo"]) == 3 and l["spans_modelo_validos"] is True


@pytest.mark.parametrize("fila", [{**FILA, "pasos": 2},                  # another warm-up task's call leaked in
                                  {**FILA, "spans_completos": False}])   # spans incomplete or not the task's own
def test_spans_de_modelo_que_no_cuadran_con_la_tarea_no_dan_columnas(fila):
    (l,) = CORR.columnas({"calentamiento": [fila]}, [{"id": "s03-es", "fase": "calentamiento"}])
    assert l["spans_modelo_validos"] is False
    assert all(l[k] is None for k in ("pasos_modelo", "aciertos_cache", "latencia_primer_paso_ms",
                                      "latencia_pasos_siguientes_ms_mediana"))


def test_un_paso_que_pudo_leer_y_no_leyo_es_un_fallo():
    pasos = [{"lectura": 0, "escritura": 0}, {"lectura": 0, "escritura": 4300}, {"lectura": 0, "escritura": 4700},
             {"lectura": 4700, "escritura": 300}]
    assert CORR.aciertos(pasos) == {"posibles": 2, "leyeron": 1, "tasa": 0.5}
