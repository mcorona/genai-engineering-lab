"""Preparación de la semana 17, sin API: el plan, las versiones candidatas fijadas, las dependencias del grupo semana17,
el verificador de entorno, los workflows y los datos de la semana 13 de los que parten las actividades 4 y 7."""
import importlib.util
import json
import re
import tomllib
from pathlib import Path

import yaml

S17 = Path(__file__).resolve().parents[1]
RAIZ = S17.parent
V = json.loads((S17 / "preparar" / "versiones.json").read_text(encoding="utf-8"))
PLAN = (S17 / "Fas4Sema17.md").read_text(encoding="utf-8")


def test_plan_tiene_10_actividades_con_tiempo_y_costo():
    actividades = re.split(r"^### ", PLAN, flags=re.M)[1:]
    assert [int(a.split(".", 1)[0]) for a in actividades] == list(range(1, 11))
    for a in actividades:
        assert "**Time:**" in a and "**Cost:**" in a, a.split("\n", 1)[0]
    for seccion in ("## Preparation", "## Dependencies and parallel work", "## Summary", "## Log"):
        assert seccion in PLAN
    assert "Criterion 17" in PLAN


def test_versiones_fijadas_y_cada_imagen_con_su_digest():
    assert set(V["digests"]) == set(V["imagenes"])                  # activity 1 pinned every image by digest
    for nombre, digest in V["digests"].items():
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest), nombre
    for nombre in ("langfuse-web", "langfuse-worker", "clickhouse", "otel-collector", "keycloak"):
        assert re.fullmatch(r"\d+\.\d+\.\d+(\.\d+)?", V["imagenes"][nombre].rsplit(":", 1)[1]), nombre
    for paquete, version in V["python"].items():
        assert re.fullmatch(r"\d+\.\d+(\.\d+|b\d+)", version), paquete
    puertos = list(V["puertos"].values())
    assert len(puertos) == len(set(puertos)) and V["puertos"]["langfuse-web"] != 3000


def test_grupo_semana17_coincide_con_versiones_y_el_lock():
    py = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    grupo = {d.split("==")[0]: d.split("==")[1] for d in py["dependency-groups"]["semana17"]}
    assert grupo == V["python"]
    lock = (RAIZ / "uv.lock").read_text(encoding="utf-8")
    for paquete, version in V["python"].items():
        assert re.search(rf'name = "{re.escape(paquete)}"\nversion = "{re.escape(version)}"', lock), paquete


def test_workflows_regresion_y_eval_semana_17():
    regresion = yaml.safe_load((RAIZ / ".github" / "workflows" / "evals-semana-06.yml").read_text())
    rutas = regresion.get("on", regresion.get(True))["pull_request"]["paths"]
    assert "semana-17/**" in rutas
    w = yaml.safe_load((RAIZ / ".github" / "workflows" / "eval-semana-17.yml").read_text())
    rutas17 = w.get("on", w.get(True))["pull_request"]["paths"]
    assert "semana-17/**" in rutas17 and "!semana-17/**/*.md" in rutas17
    pasos = " ".join(str(p.get("run", "")) for p in w["jobs"]["sin-api"]["steps"])
    for paquete, version in V["python"].items():
        assert f'"{paquete}=={version}"' in pasos, paquete           # CI installs the same pins
    assert "verificar_entorno.py --sin-docker" in pasos and "SKIPPED" in pasos


def test_gitignore_cubre_secretos_y_trazas_crudas():
    gi = (RAIZ / ".gitignore").read_text()
    assert "semana-17/**/.secretos.env" in gi and "semana-17/observabilidad/datos/" in gi


def test_datos_de_la_semana_13_para_actividades_4_y_7():
    tareas = [json.loads(x) for lang in ("es", "en")
              for x in (RAIZ / "semana-13" / "golden" / f"tareas_{lang}.jsonl").read_text().splitlines() if x.strip()]
    assert len(tareas) == 84
    filas = [json.loads(x) for x in (RAIZ / "semana-13" / "resultados" / "eval_sdk_low_detalle.jsonl")
             .read_text().splitlines() if x.strip()]
    assert {f["id"] for f in filas} == {t["id"] for t in tareas}
    for k in ("costo_usd", "tokens_in", "tokens_out", "pasos", "pasos_min", "herramientas", "exito"):
        assert all(k in f for f in filas), k


def test_verificador_sin_docker_corre_y_no_muestra_dsn(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("verificar17", S17 / "preparar" / "verificar_entorno.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setenv("PG_DSN", "postgresql://u:una-clave-secreta@127.0.0.1:1/x")
    monkeypatch.delenv("PG_ADMIN_DSN", raising=False)
    r = m.revisar(sin_docker=True)
    nombres = [n for n, _, _ in r]
    assert not any(n.startswith(("imagen ", "memoria", "disco")) for n in nombres)
    m.main(["--sin-docker"])
    salida = capsys.readouterr().out
    assert "una-clave-secreta" not in salida and "postgresql://" not in salida
