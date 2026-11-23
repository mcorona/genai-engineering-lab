"""Week 20, activity 1: the agent's per-task budget is chosen at synth time (PRESUPUESTO_TAREA), and the default
leaves the week 19 template unchanged.

Runs in the spike-iac job (needs aws-cdk-lib). Synthesizes lab with COMPUTO=1 and reads the agent function's
environment from the semana19-computo template."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
APP = S19 / "infra" / "cdk" / "app.py"
MANEJADOR_AGENTE = "app.consultas.worker.handler_lambda"


def _sintetizar(presupuesto: str | None) -> subprocess.CompletedProcess:
    salida = Path(tempfile.mkdtemp(prefix="s19-presupuesto-"))
    entorno = {**os.environ, "PERFIL": "lab", "CDK_OUTDIR": str(salida), "COMPUTO": "1", "S19_SIN_DEPENDENCIAS": "1",
               "JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION": "1"}
    for v in ("CAMINO_HERRAMIENTAS", "S19_GATEWAY_FASE", "S19_GATEWAY_URL", "PRESUPUESTO_TAREA"):
        entorno.pop(v, None)
    if presupuesto is not None:
        entorno["PRESUPUESTO_TAREA"] = presupuesto
    r = subprocess.run([sys.executable, str(APP)], env=entorno, capture_output=True, text=True)
    r.salida = salida
    return r


def _entorno_del_agente(salida: Path) -> dict:
    plantilla = json.loads((salida / "semana19-computo.template.json").read_text(encoding="utf-8"))
    [agente] = [r for r in plantilla["Resources"].values()
                if r["Type"] == "AWS::Lambda::Function" and r["Properties"].get("Handler") == MANEJADOR_AGENTE]
    return agente["Properties"]["Environment"]["Variables"]


@pytest.mark.parametrize("valor, esperado", [(None, None), ("semana17", None), ("techo_semana20", "techo_semana20")])
def test_el_presupuesto_llega_al_agente_solo_si_no_es_el_de_la_semana_17(valor, esperado):
    r = _sintetizar(valor)
    assert r.returncode == 0, r.stderr[-2000:]
    assert _entorno_del_agente(r.salida).get("PRESUPUESTO_TAREA") == esperado


def test_un_presupuesto_desconocido_detiene_la_sintesis():
    r = _sintetizar("sin_tope")
    assert r.returncode != 0 and "PRESUPUESTO_TAREA desconocido" in r.stderr
