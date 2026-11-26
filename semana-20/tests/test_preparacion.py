"""Week 20, preparation: offline tests ($0, no AWS, no model).

The plan's structure, the pins, the CI paths that make `regresion` run this week, the readiness check in CI mode,
and that the folder holds no personal data.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
S20 = RAIZ / "semana-20"
PLAN = S20 / "Fas5Sema20.md"
VERSIONES = json.loads((S20 / "preparar" / "versiones.json").read_text(encoding="utf-8"))
PIN = re.compile(r"^\d+\.\d+(\.\d+|b\d+)$")   # exact: X.Y.Z, or X.YbN (the OpenTelemetry pre-releases of week 17)
FLUJO = RAIZ / ".github" / "workflows" / "eval-semana-20.yml"


def cargar(ruta: Path, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def actividades() -> dict[str, str]:
    seccion = PLAN.read_text(encoding="utf-8").split("## Activities", 1)[1].split("\n## ", 1)[0]
    partes = re.split(r"^### ", seccion, flags=re.M)[1:]
    return {p.split("\n", 1)[0]: p for p in partes}


# ---------- plan ----------

def test_plan_sin_seccion_de_traspaso():
    texto = PLAN.read_text(encoding="utf-8")
    assert "## Para Claude CLI" not in texto
    assert "Primer mensaje sugerido" not in texto


def test_plan_tiene_diez_actividades_con_time_cost_y_aip():
    acts = actividades()
    assert [t.split(".", 1)[0] for t in acts] == [str(n) for n in range(1, 11)], list(acts)
    for titulo, cuerpo in acts.items():
        assert re.search(r"^- \*\*Time:\*\* ~\d+(\.\d+)? h", cuerpo, re.M), f"no Time: {titulo}"
        assert "**Cost:** " in cuerpo, f"no Cost: {titulo}"
        assert re.search(r"^- \*\*AIP-C01:\*\* .*\bD[1-5]\b", cuerpo, re.M), f"no AIP-C01 domain: {titulo}"


def test_plan_criterio_20_y_regla_de_la_semana_10():
    texto = PLAN.read_text(encoding="utf-8")
    assert "**Criterion 20 (root README):**" in texto
    assert "week 10 rule" in texto


def test_plan_no_compra_throughput_aprovisionado():
    cuerpo = actividades()["6. Capacity: throttling, quotas and provisioned throughput"]
    assert "Nothing is bought." in cuerpo
    assert "H2 and H10" in cuerpo


# ---------- pins ----------

def _grupo(nombre: str) -> list[str]:
    pyproject = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    return re.findall(r'"([^"]+)"', pyproject.split(f"{nombre} = [", 1)[1].split("]", 1)[0])


def test_grupo_semana20_pins_exactos_y_igual_a_versiones_json():
    entradas = _grupo("semana20")
    assert entradas == [f"{p}=={v}" for p, v in VERSIONES["python"].items()]
    for p, v in VERSIONES["python"].items():
        assert PIN.match(v), f"{p} is not an exact pin: {v}"


def test_pines_vienen_de_grupos_ya_verificados():
    for paquete, version in VERSIONES["python"].items():
        origen = VERSIONES["origen"][paquete]
        assert f"{paquete}=={version}" in _grupo(origen), f"{paquete}=={version} is not in the {origen} group"


def test_uv_lock_tiene_el_grupo_semana20():
    lock = (RAIZ / "uv.lock").read_text(encoding="utf-8")
    assert "semana20 = [" in lock
    assert re.search(r'name = "opentelemetry-sdk"\nversion = "1\.45\.2"', lock)


def test_versiones_no_usan_etiquetas_flotantes():
    texto = json.dumps(VERSIONES["python"])
    for palabra in ('"latest"', '"stable"', '">=', '"^', '"~', '"*"'):
        assert palabra not in texto


# ---------- CI ----------

def test_regresion_incluye_semana20():
    flujo = (RAIZ / ".github" / "workflows" / "evals-semana-06.yml").read_text(encoding="utf-8")
    assert '"semana-20/**"' in flujo.split("paths:", 1)[1].split("jobs:", 1)[0]
    assert "regresion:" in flujo


def test_eval_semana_20_sin_aws_sin_skips_y_con_los_pines():
    flujo = FLUJO.read_text(encoding="utf-8")
    assert not re.search(r"aws-actions|AWS_|aws configure|aws sts|aws login|secrets\.", flujo)
    assert "verificar_entorno.py --ci" in flujo and "semana-20/tests" in flujo
    assert 'grep -q "SKIPPED"' in flujo
    for paquete, version in VERSIONES["python"].items():
        assert f'"{paquete}=={version}"' in flujo


def test_verificar_entorno_ci_sin_aws():
    r = subprocess.run([sys.executable, str(S20 / "preparar" / "verificar_entorno.py"), "--ci"],
                       capture_output=True, text=True, timeout=120)
    informe = json.loads(r.stdout)
    assert informe["modo"] == "ci"
    assert informe["linea_base_semana19"]["ok"] and informe["linea_base_semana19"]["con_costo"] == 19
    assert all(informe["traspaso"].values()), informe["traspaso"]
    assert all(informe["rutas_ci"].values()), informe["rutas_ci"]
    assert "sesiones" not in informe and "sintesis_semana19" not in informe
    # The pins are only installed in CI (the semana20 group); locally the rest must still pass.
    if all(p["ok"] for p in informe["paquetes_python"].values()):
        assert r.returncode == 0 and informe["ok"] is True


def test_linea_base_detecta_lineas_malas(tmp_path):
    V = cargar(S20 / "preparar" / "verificar_entorno.py", "verificar_entorno_s20")
    ruta = tmp_path / "b.jsonl"
    ruta.write_text('{"id": "x"}\nno es json\n', encoding="utf-8")
    r = V.linea_base(ruta)
    assert r["ok"] is False and r["lineas_malas"] == [1, 2]
    assert V.linea_base(tmp_path / "no.jsonl") == {"ok": False, "motivo": "no existe"}


# ---------- higiene ----------

def test_semana20_sin_correos_ni_rutas_personales():
    correo = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
    rutas = re.compile(r"/Users/|/home/")
    r = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", "semana-20"],
                       cwd=RAIZ, capture_output=True, text=True, timeout=60)
    for f in r.stdout.split():
        ruta = RAIZ / f
        if not ruta.is_file() or "__pycache__" in ruta.parts or ruta.resolve() == Path(__file__).resolve():
            continue
        texto = ruta.read_text(encoding="utf-8", errors="ignore")
        assert not correo.search(texto), f"email in {f}"
        assert not rutas.search(texto), f"personal path in {f}"
