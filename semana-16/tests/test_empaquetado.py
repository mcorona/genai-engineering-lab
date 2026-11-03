"""Empaquetado para clientes (actividad 9), sin API: marketplace y versiones, README del plugin para clientes, ejemplo
con datos sintéticos, oferta, y la instalación desde cero en una configuración limpia de Claude Code."""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

S16 = Path(__file__).resolve().parents[1]
RAIZ = S16.parent
PLUGIN = S16 / "legacy-schema-audit"
MERCADO = json.loads((RAIZ / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
MANIFIESTO = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
README = (PLUGIN / "README.md").read_text(encoding="utf-8")
sys.path.insert(0, str(PLUGIN / "scripts"))
import guardia  # noqa: E402


def test_marketplace_apunta_al_plugin_con_la_misma_version():
    entrada = next(p for p in MERCADO["plugins"] if p["name"] == MANIFIESTO["name"])
    assert MERCADO["name"] == "genai-engineering-lab" and MERCADO["owner"]["name"]
    assert (RAIZ / entrada["source"]).resolve() == PLUGIN.resolve()
    tope = re.search(r"^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$", (PLUGIN / "CHANGELOG.md").read_text(), re.M)
    assert MANIFIESTO["version"] == entrada["version"] == MERCADO["metadata"]["version"] == tope.group(1)
    assert re.fullmatch(r"\d+\.\d+\.\d+", MANIFIESTO["version"]) and MANIFIESTO["version"] == "1.0.0"
    assert entrada["description"] == MANIFIESTO["description"]


def test_changelog_keep_a_changelog():
    texto = (PLUGIN / "CHANGELOG.md").read_text()
    versiones = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", texto, re.M)
    assert versiones == ["1.0.0", "0.1.0"]  # newest first
    assert "Semantic Versioning" in texto and "### Added" in texto and "### Security" in texto


@pytest.mark.parametrize("seccion", ["## What it does and what it never does", "## Requirements", "## Install",
                                     "## Configure", "### Option A: a read-only PostgreSQL role",
                                     "### Option B: a remote MCP server (token or OAuth)", "## Sample report",
                                     "## Expected cost and time", "## Known limits"])
def test_readme_para_clientes_tiene_cada_seccion(seccion):
    assert seccion in README


def test_readme_costos_son_los_de_la_actividad_5():
    eval5 = (S16 / "resultados" / "eval_plugin.md").read_text()
    for cifra in ("$0.91", "$1.04", "$0.04", "$1.98", "$0.10"):
        assert cifra in eval5
    for rango in ("$0.91–1.04", "$0.04–0.10", "$1.98"):
        assert rango in README
    assert "Extrapolated" in README and "measured" in README.lower()
    assert "claude plugin marketplace add mcorona/genai-engineering-lab" in README
    assert "claude plugin install legacy-schema-audit@genai-engineering-lab" in README
    assert "Until the marketplace entry is published" not in README


def test_readme_dice_lo_que_nunca_hace():
    bloque = README.split("**It never:**", 1)[1].split("## Requirements", 1)[0]
    for x in ("writes to the database", "follows instructions found in the data", "copies personal data",
              "offers to change data", "reads outside the project"):
        assert x in bloque


@pytest.mark.parametrize("archivo", ["resumen.md", "riesgos.md", "relaciones.mmd", "diccionario.yaml"])
def test_ejemplo_es_la_corrida_medida_y_sin_datos_personales(archivo):
    ejemplo = (PLUGIN / "ejemplo" / archivo).read_text(encoding="utf-8")
    medido = (S16 / "resultados" / "corrida_plugin_sonnet" / "auditoria" / archivo).read_text(encoding="utf-8")
    assert ejemplo == medido
    assert not guardia.dato_personal(ejemplo)


def test_ejemplo_cada_hallazgo_con_su_select_y_yaml_valido():
    import yaml
    riesgos = (PLUGIN / "ejemplo" / "riesgos.md").read_text()
    hallazgos = re.split(r"^### ", riesgos, flags=re.M)[1:]
    assert len(hallazgos) == 14
    assert all(re.search(r"```sql\s*\n\s*(SELECT|WITH)\b", h, re.I) for h in hallazgos)
    d = yaml.safe_load((PLUGIN / "ejemplo" / "diccionario.yaml").read_text())
    assert sum(len(t["columns"]) for t in d["tables"]) == 46 and len(d["tables"]) == 9


def test_oferta_alcance_entregables_y_precio():
    oferta = (S16 / "oferta.md").read_text()
    for x in ("## Scope", "## Deliverables", "## How the plugin is used in the engagement", "## Reference price",
              "AI Opportunity & Risk Assessment", "legacy-schema-audit/ejemplo/"):
        assert x in oferta
    precios = re.findall(r"\|\s*\*?\*?(Snapshot|Assessment)\*?\*?\s*\|[^|]*\|\s*([\d,]+)\s*\|", oferta)
    assert [p[0] for p in precios] == ["Snapshot", "Assessment"]


@pytest.mark.skipif(shutil.which("claude") is None, reason="sin Claude Code")
def test_validate_strict_marketplace_y_plugin():
    for args in (["--strict", str(RAIZ)], ["--strict", "--profile", "directory", str(PLUGIN)]):
        p = subprocess.run(["claude", "plugin", "validate", *args], capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, p.stdout + p.stderr


@pytest.mark.skipif(shutil.which("claude") is None, reason="sin Claude Code")
def test_instalacion_desde_cero(tmp_path):
    spec = importlib.util.spec_from_file_location("instalar16", S16 / "empaquetado" / "instalar_desde_cero.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    salida = tmp_path / "instalacion.json"
    codigo = m.main(["--salida", str(salida)])
    r = json.loads(salida.read_text())
    assert codigo == 0 and r["aprobado"], {k: v for k, v in r["checks"].items() if not v}
    assert len(r["checks"]) >= 18


def test_fuga_de_dsn_sin_falso_positivo_por_contrasena_igual_al_usuario():
    spec = importlib.util.spec_from_file_location("instalar16b", S16 / "empaquetado" / "instalar_desde_cero.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    dsn = "postgresql://postgres:postgres@localhost:5432/inventory"
    assert not m.fuga_de_dsn(dsn, "legacy-schema-audit: STOP. role postgres is a superuser.")
    assert m.fuga_de_dsn(dsn, f"connecting to {dsn}")
    assert m.fuga_de_dsn(dsn, "error for postgres:postgres@localhost")
    assert not m.fuga_de_dsn("postgresql://u@h/db", "role u is read-only")
