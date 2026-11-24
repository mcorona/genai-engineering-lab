"""Week 20, preparation: every week 19 stack carries the cost allocation tags proyecto, perfil and componente.

Runs in the spike-iac job (needs aws-cdk-lib). Synthesizes lab and prod with COMPUTO=1 and reads the stack tags from
the cloud assembly manifest and the tags CloudFormation would put on each taggable resource."""
from __future__ import annotations

import json
import os
import re
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


# Week 20, activity 2: each application inference profile carries its component's name, not the stack's (ia).
PERFILES_DE_APLICACION = {"PerfilAgente": "agente", "PerfilJuez": "juez", "PerfilEnriquecimiento": "enriquecimiento"}


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
            esperado = PERFILES_DE_APLICACION.get(lid, nombre.removeprefix("semana19-"))
            if claves.get("componente") != esperado:
                sin.append((nombre, lid))
    assert not sin, sin
    computo = plantillas["semana19-computo"]["Resources"]
    funciones = [r for r in computo.values() if r["Type"] == "AWS::Lambda::Function"]
    assert funciones and all({"Key": "componente", "Value": "computo"} in r["Properties"]["Tags"] for r in funciones)


# ---------------------------------------------------------------- week 20, activity 2: application inference profiles

def _sintetizar_sin_perfil() -> dict:
    """The same synth with ia/config.py's switch off (USAR_PERFIL_DE_APLICACION = False), set before app.py reads it."""
    salida = Path(tempfile.mkdtemp(prefix="s19-sin-perfil-"))
    entorno = {**os.environ, "PERFIL": "lab", "CDK_OUTDIR": str(salida), "COMPUTO": "1", "S19_SIN_DEPENDENCIAS": "1",
               "JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION": "1"}
    for v in ("CAMINO_HERRAMIENTAS", "S19_GATEWAY_FASE", "S19_GATEWAY_URL"):
        entorno.pop(v, None)
    codigo = ("import runpy, sys; sys.path[:0] = [sys.argv[1], sys.argv[2]]; from ia import config; "
              "config.USAR_PERFIL_DE_APLICACION = False; runpy.run_path(sys.argv[3], run_name='__main__')")
    r = subprocess.run([sys.executable, "-c", codigo, str(S19), str(APP.parent), str(APP)], env=entorno,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    manifiesto = json.loads((salida / "manifest.json").read_text(encoding="utf-8"))
    return {k: json.loads((salida / a["properties"]["templateFile"]).read_text(encoding="utf-8"))
            for k, a in manifiesto["artifacts"].items() if a.get("type") == "aws:cloudformation:stack"}


def _agente(plantillas: dict) -> tuple[dict, dict]:
    """The agent function and its role's policy statements, from the computo template."""
    rec = plantillas["semana19-computo"]["Resources"]
    (funcion,) = [r for r in rec.values() if r["Type"] == "AWS::Lambda::Function"
                  and r["Properties"].get("Handler") == "app.consultas.worker.handler_lambda"]
    rol = funcion["Properties"]["Role"]["Fn::GetAtt"][0]
    sts = {s.get("Sid"): s for r in rec.values() if r["Type"] == "AWS::IAM::Policy"
           and {"Ref": rol} in r["Properties"].get("Roles", []) for s in r["Properties"]["PolicyDocument"]["Statement"]}
    return funcion, sts


def test_un_perfil_de_aplicacion_por_componente_copia_su_perfil_de_sistema():
    sys.path.insert(0, str(S19))
    from ia import config
    _, plantillas = ensamblado("lab")
    perfiles = {lid: r["Properties"] for lid, r in plantillas["semana19-ia"]["Resources"].items()
                if r["Type"] == "AWS::Bedrock::ApplicationInferenceProfile"}
    assert set(perfiles) == set(PERFILES_DE_APLICACION)
    for lid, p in perfiles.items():
        componente = PERFILES_DE_APLICACION[lid]
        assert p["InferenceProfileName"] == f"semana19-{componente}"
        origen = json.dumps(p["ModelSource"]["CopyFrom"])
        assert origen.endswith(f':inference-profile/{config.PERFILES_DE_APLICACION[componente]}"]]}}'), origen
        etiquetas = {e["Key"]: e["Value"] for e in p["Tags"]}
        assert etiquetas["componente"] == componente and etiquetas["proyecto"] == "semana19"
        # The resource schema's patterns (2026-11-24: a comma in Description failed ia's early validation).
        assert re.fullmatch(r"([0-9a-zA-Z:.][ _-]?)+", p["Description"]), p["Description"]
        assert re.fullmatch(r"([0-9a-zA-Z][ _-]?)+", p["InferenceProfileName"]), p["InferenceProfileName"]


def test_el_agente_llama_su_perfil_de_aplicacion_y_ningun_otro_modelo():
    sys.path.insert(0, str(S19))
    from ia import config
    _, plantillas = ensamblado("lab")
    funcion, sts = _agente(plantillas)
    modelo = funcion["Properties"]["Environment"]["Variables"]["MODELO"]
    assert "Fn::ImportValue" in modelo and "PerfilAgente" in json.dumps(modelo)
    recursos = sts["ModeloDeHaikuPorConverse"]["Resource"]
    assert recursos[0] == modelo                                  # the same profile the Lambda calls
    assert json.dumps(recursos[1]).endswith(f'foundation-model/{config.MODELO_ID.split(".", 1)[1]}"]]}}')
    assert len(recursos) == 2 and sts["ModeloDeHaikuPorConverse"]["Action"] == "bedrock:InvokeModel"
    otros = [s for sid, s in sts.items() if sid != "ModeloDeHaikuPorConverse" and "bedrock:InvokeModel" in json.dumps(s)]
    assert not otros


def test_apagar_el_perfil_es_un_cambio_de_configuracion_y_vuelve_al_perfil_de_sistema():
    sys.path.insert(0, str(S19))
    from ia import config
    plantillas = _sintetizar_sin_perfil()
    funcion, sts = _agente(plantillas)
    assert funcion["Properties"]["Environment"]["Variables"]["MODELO"] == config.MODELO_ID
    assert json.dumps(sts["ModeloDeHaikuPorConverse"]["Resource"][0]).endswith(
        f':inference-profile/{config.MODELO_ID}"]]}}')
