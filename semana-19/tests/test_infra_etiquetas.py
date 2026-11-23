"""Week 20, preparation: every week 19 stack carries the cost allocation tags proyecto, perfil and componente.

Runs in the spike-iac job (needs aws-cdk-lib). Synthesizes lab and prod with COMPUTO=1 and reads the stack tags from
the cloud assembly manifest and the tags CloudFormation would put on each taggable resource."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
APP = S19 / "infra" / "cdk" / "app.py"
PILAS = {"semana19-control", "semana19-base", "semana19-datos", "semana19-ia", "semana19-computo", "semana19-gateway",
         "semana19-agentes-comparacion", "semana19-eval"}


@lru_cache(maxsize=2)
def ensamblado(perfil: str) -> tuple[dict, dict]:
    salida = Path(tempfile.mkdtemp(prefix=f"s19-etiquetas-{perfil}-"))
    entorno = {**os.environ, "PERFIL": perfil, "CDK_OUTDIR": str(salida), "COMPUTO": "1", "S19_SIN_DEPENDENCIAS": "1",
               "JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION": "1"}
    for v in ("CAMINO_HERRAMIENTAS", "S19_GATEWAY_FASE", "S19_GATEWAY_URL"):
        entorno.pop(v, None)
    r = subprocess.run([sys.executable, str(APP)], env=entorno, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    manifiesto = json.loads((salida / "manifest.json").read_text(encoding="utf-8"))
    pilas = {k: a for k, a in manifiesto["artifacts"].items() if a.get("type") == "aws:cloudformation:stack"}
    plantillas = {k: json.loads((salida / a["properties"]["templateFile"]).read_text(encoding="utf-8"))
                  for k, a in pilas.items()}
    return pilas, plantillas


@pytest.mark.parametrize("perfil", ["lab", "prod"])
def test_cada_pila_lleva_proyecto_perfil_y_componente(perfil):
    pilas, _ = ensamblado(perfil)
    assert set(pilas) == PILAS
    for nombre, a in pilas.items():
        assert a["properties"].get("tags") == {"proyecto": "semana19", "perfil": perfil,
                                               "componente": nombre.removeprefix("semana19-")}, nombre


@pytest.mark.parametrize("perfil", ["lab", "prod"])
def test_los_recursos_etiquetables_llevan_componente(perfil):
    _, plantillas = ensamblado(perfil)
    sin = []
    for nombre, pl in plantillas.items():
        for lid, r in pl["Resources"].items():
            etiquetas = r.get("Properties", {}).get("Tags")
            if isinstance(etiquetas, list) and etiquetas and isinstance(etiquetas[0], dict) and "Key" in etiquetas[0]:
                claves = {e["Key"]: e["Value"] for e in etiquetas}      # the list form (most resource types)
            elif isinstance(etiquetas, dict):
                claves = etiquetas                                       # the map form (Bedrock, AgentCore)
            else:
                continue
            if claves.get("componente") != nombre.removeprefix("semana19-"):
                sin.append((nombre, lid))
    assert not sin, sin
    computo = plantillas["semana19-computo"]["Resources"]
    funciones = [r for r in computo.values() if r["Type"] == "AWS::Lambda::Function"]
    assert funciones and all({"Key": "componente", "Value": "computo"} in r["Properties"]["Tags"] for r in funciones)
