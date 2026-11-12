"""Week 19, preparation: offline tests ($0, no AWS, no model).

They check the plan's structure, the pins, the CI paths that make `regresion` run this week, the .gitignore entries,
the budget in simulation, the readiness check in CI mode, and that the folder holds no personal data.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
S19 = RAIZ / "semana-19"
PLAN = S19 / "Fas5Sema19.md"
VERSIONES = json.loads((S19 / "preparar" / "versiones.json").read_text(encoding="utf-8"))
PIN = re.compile(r"^\d+\.\d+\.\d+$")


def cargar(ruta: Path, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def actividades() -> dict[str, str]:
    texto = PLAN.read_text(encoding="utf-8")
    seccion = texto.split("## Activities", 1)[1]
    partes = re.split(r"^### ", seccion, flags=re.M)[1:]
    return {p.split("\n", 1)[0]: p for p in partes}


# ---------- plan ----------

def test_plan_sin_seccion_de_traspaso():
    assert "Para Claude CLI" not in PLAN.read_text(encoding="utf-8")


def test_plan_tiene_diez_actividades_con_time_cost_y_aip():
    acts = actividades()
    assert len(acts) == 10, list(acts)
    for titulo, cuerpo in acts.items():
        assert re.search(r"^- \*\*Time:\*\* ~\d+(\.\d+)? h", cuerpo, re.M), f"sin Time: {titulo}"
        assert re.search(r"\*\*Cost:\*\* ", cuerpo), f"sin Cost: {titulo}"
        m = re.search(r"^- \*\*AIP-C01:\*\* .*\bD[1-5]\b", cuerpo, re.M)
        assert m, f"sin dominio AIP-C01: {titulo}"


def test_plan_actividad_1_es_solo_lectura_y_costo_cero():
    cuerpo = actividades()["1. Baseline: the account, the services and the prices"]
    assert "read-only" in cuerpo
    assert "**Cost:** $0" in cuerpo


# ---------- pins ----------

def test_grupo_semana19_pins_exactos():
    pyproject = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    bloque = pyproject.split("semana19 = [", 1)[1].split("]", 1)[0]
    entradas = re.findall(r'"([^"]+)"', bloque)
    assert entradas, "el grupo semana19 está vacío"
    for e in entradas:
        assert re.fullmatch(r"[a-z0-9\-]+==\d+\.\d+\.\d+", e), f"pin no exacto: {e}"


def test_versiones_python_son_pines_exactos():
    for paquete, version in VERSIONES["python"].items():
        assert PIN.match(version), f"{paquete} no es un pin exacto: {version}"


def test_versiones_no_usan_etiquetas_flotantes():
    texto = json.dumps(VERSIONES)
    for palabra in ('"latest"', '"stable"', '">=', '"^', '"~', '"*"'):
        assert palabra not in texto, f"etiqueta flotante en versiones.json: {palabra}"


def test_grupo_semana19_coincide_con_versiones_json():
    pyproject = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    for paquete, version in VERSIONES["python"].items():
        assert f'"{paquete}=={version}"' in pyproject, f"{paquete} distinto entre pyproject y versiones.json"


def test_uv_lock_tiene_el_grupo_semana19():
    lock = (RAIZ / "uv.lock").read_text(encoding="utf-8")
    assert "semana19 = [" in lock
    assert re.search(r'name = "moto"\nversion = "5\.2\.5"', lock)
    assert re.search(r'name = "boto3"\nversion = "1\.43\.122"', lock)


def test_workflow_eval_19_pins_exactos_y_sin_flotantes():
    flujo = (RAIZ / ".github" / "workflows" / "eval-semana-19.yml").read_text(encoding="utf-8")
    for paquete, version in VERSIONES["python"].items():
        assert f'"{paquete}=={version}"' in flujo, f"el workflow no fija {paquete}=={version}"


# ---------- CI ----------

def test_regresion_incluye_semana19():
    flujo = (RAIZ / ".github" / "workflows" / "evals-semana-06.yml").read_text(encoding="utf-8")
    paths = flujo.split("paths:", 1)[1].split("jobs:", 1)[0]
    assert '"semana-19/**"' in paths
    assert "regresion:" in flujo


def test_eval_semana_19_sin_aws_ni_skips():
    flujo = (RAIZ / ".github" / "workflows" / "eval-semana-19.yml").read_text(encoding="utf-8")
    assert not re.search(r"aws-actions|AWS_|aws configure|aws sts|aws login", flujo)
    assert "verificar_entorno.py --ci" in flujo
    assert "semana-19/tests" in flujo
    assert 'grep -q "SKIPPED"' in flujo


def test_gitignore_tiene_las_entradas_de_la_semana19():
    gi = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
    for entrada in ("cdk.out/", ".terraform/", "*.tfstate*", "semana-19/**/.secretos.env"):
        assert entrada in gi, f"falta en .gitignore: {entrada}"


def test_readme_raiz_tiene_fase_5_con_criterios_19_a_22():
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    assert "### Phase 5" in readme
    for n in ("19.", "20.", "21.", "22."):
        assert f"| {n} " in readme or f"{n} " in readme
    assert "±20%" in readme


# ---------- presupuesto (simulación) ----------

@pytest.fixture(scope="module")
def presupuesto():
    return cargar(S19 / "infra" / "presupuesto.py", "presupuesto_s19")


def test_presupuesto_nombre_limite_y_alertas(presupuesto):
    req = presupuesto.construir_presupuesto(None)
    assert req["Budget"]["BudgetName"] == "semana19"
    assert req["Budget"]["BudgetLimit"] == {"Amount": "5", "Unit": "USD"}
    assert req["Budget"]["TimeUnit"] == "MONTHLY"
    assert req["Budget"]["CostFilters"] == {"TagKeyValue": ["user:proyecto$semana19"]}
    alertas = [(n["Notification"]["NotificationType"], n["Notification"]["Threshold"])
               for n in req["NotificationsWithSubscribers"]]
    assert alertas == [("ACTUAL", 50.0), ("ACTUAL", 100.0), ("FORECASTED", 100.0)]


def test_presupuesto_correo_sale_del_entorno_no_del_repo(presupuesto):
    simulado = json.dumps(presupuesto.construir_presupuesto(None))
    assert "<correo de ALERTA_EMAIL>" in simulado
    real = presupuesto.construir_presupuesto("alertas@ejemplo.test")
    assert real["NotificationsWithSubscribers"][0]["Subscribers"][0]["Address"] == "alertas@ejemplo.test"


def test_presupuesto_por_omision_es_simulacion(presupuesto, capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["presupuesto.py"])
    monkeypatch.delenv("ALERTA_EMAIL", raising=False)
    assert presupuesto.main() == 0
    salida = capsys.readouterr().out
    assert '"modo": "simulacion"' in salida


def test_presupuesto_si_sin_correo_o_perfil_no_llama_a_aws(presupuesto, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["presupuesto.py", "--si"])
    monkeypatch.delenv("ALERTA_EMAIL", raising=False)
    assert presupuesto.main() == 2


# ---------- verificador en modo CI ----------

def test_verificar_entorno_ci_sin_aws():
    r = subprocess.run([sys.executable, str(S19 / "preparar" / "verificar_entorno.py"), "--ci"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-400:]
    informe = json.loads(r.stdout)
    assert informe["modo"] == "ci"
    assert informe["ok"] is True
    assert "herramientas" not in informe and "sesiones" not in informe


# ---------- higiene: sin datos personales ni rutas del Mac ----------

def test_semana19_sin_correos_ni_rutas_personales():
    correo = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
    rutas = re.compile(r"/Users/|/home/")
    for ruta in S19.rglob("*"):
        if not ruta.is_file() or ruta.suffix in {".pyc"} or ruta.resolve() == Path(__file__).resolve():
            continue
        if "__pycache__" in ruta.parts or ".pytest_cache" in ruta.parts:
            continue
        texto = ruta.read_text(encoding="utf-8", errors="ignore")
        assert not correo.search(texto), f"correo en {ruta.relative_to(RAIZ)}"
        assert not rutas.search(texto), f"ruta personal en {ruta.relative_to(RAIZ)}"
