"""Week 20, activity 4, R1: the router's profiles and IAM, chosen at synth time with RUTEO (ADR 0015 sections 5 and 6).

Runs in the spike-iac job (needs aws-cdk-lib). With RUTEO absent or off the templates are today's. With r1: one
application inference profile per new candidate (semana19-agente-nova-lite, semana19-agente-sonnet-4-6), tagged
componente=agente; the agent Lambda receives RUTEO and each candidate's profile ARN; its role allows InvokeModel on
exactly the candidates' profiles and foundation models; the boundary has room for them; cdk-nag stays at zero with no
suppression added."""
from __future__ import annotations

import csv
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
MANEJADOR_AGENTE = "app.consultas.worker.handler_lambda"
NOVA, HAIKU, SONNET = "us.amazon.nova-lite-v1:0", "us.anthropic.claude-haiku-4-5-20251001-v1:0", \
    "us.anthropic.claude-sonnet-4-6"
PERFILES_NUEVOS = {"PerfilAgenteNovaLite": ("semana19-agente-nova-lite", NOVA),
                   "PerfilAgenteSonnet46": ("semana19-agente-sonnet-4-6", SONNET)}
PILAS_NAG = ("semana19-control", "semana19-ia", "semana19-computo")


def _correr(variables: dict, perfil: str = "lab", candidatos: tuple | None = None, con_perfiles: bool = True):
    salida = Path(tempfile.mkdtemp(prefix=f"s19-ruteo-{perfil}-"))
    entorno = {**os.environ, "PERFIL": perfil, "CDK_OUTDIR": str(salida), "COMPUTO": "1", "S19_SIN_DEPENDENCIAS": "1",
               "JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION": "1"}
    for v in ("CAMINO_HERRAMIENTAS", "S19_GATEWAY_FASE", "S19_GATEWAY_URL", "PRESUPUESTO_TAREA", "CACHE_PROMPT",
              "CACHE_TTL", "RUTEO"):
        entorno.pop(v, None)
    entorno.update(variables)
    # ia/config.py read as it is, or with its candidates or its profile switch replaced before app.py reads them.
    codigo = ("import runpy, sys, json; sys.path[:0] = [sys.argv[1], sys.argv[2]]; from ia import config; "
              "c = json.loads(sys.argv[4]); c and setattr(config, 'RUTEO_CANDIDATOS', tuple(c)); "
              "config.USAR_PERFIL_DE_APLICACION = json.loads(sys.argv[5]); "
              "runpy.run_path(sys.argv[3], run_name='__main__')")
    r = subprocess.run([sys.executable, "-c", codigo, str(S19), str(APP.parent), str(APP), json.dumps(candidatos),
                        json.dumps(con_perfiles)],
                       env=entorno, capture_output=True, text=True)
    r.salida = salida
    return r


@lru_cache(maxsize=None)
def _ensamblado(ruteo: str | None, perfil: str = "lab", candidatos: tuple | None = None) -> dict:
    r = _correr({} if ruteo is None else {"RUTEO": ruteo}, perfil, candidatos)
    assert r.returncode == 0, r.stderr[-2000:]
    manifiesto = json.loads((r.salida / "manifest.json").read_text(encoding="utf-8"))
    plantillas = {k: json.loads((r.salida / a["properties"]["templateFile"]).read_text(encoding="utf-8"))
                  for k, a in manifiesto["artifacts"].items() if a.get("type") == "aws:cloudformation:stack"}
    nag = {n: list(csv.DictReader((r.salida / f"AwsSolutions--{n}-NagReport.csv").open(encoding="utf-8")))
           for n in PILAS_NAG}
    return {"plantillas": plantillas, "nag": nag}


def _perfiles(pl: dict) -> dict:
    return {lid: r["Properties"] for lid, r in pl["semana19-ia"]["Resources"].items()
            if r["Type"] == "AWS::Bedrock::ApplicationInferenceProfile"}


def _agente(pl: dict) -> tuple[dict, dict]:
    rec = pl["semana19-computo"]["Resources"]
    (funcion,) = [r for r in rec.values() if r["Type"] == "AWS::Lambda::Function"
                  and r["Properties"].get("Handler") == MANEJADOR_AGENTE]
    rol = funcion["Properties"]["Role"]["Fn::GetAtt"][0]
    sts = {s.get("Sid"): s for r in rec.values() if r["Type"] == "AWS::IAM::Policy"
           and {"Ref": rol} in r["Properties"].get("Roles", []) for s in r["Properties"]["PolicyDocument"]["Statement"]}
    return funcion["Properties"]["Environment"]["Variables"], sts


def _limite(pl: dict) -> dict:
    (limite,) = [r for r in pl["semana19-control"]["Resources"].values() if r["Type"] == "AWS::IAM::ManagedPolicy"
                 and r["Properties"].get("ManagedPolicyName") == "semana19-limite"]
    return {s["Sid"]: s for s in limite["Properties"]["PolicyDocument"]["Statement"]}


def _texto(x) -> str:
    return json.dumps(x, sort_keys=True)


# --- off is today's ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("ruteo", [None, "off"])
def test_without_ruteo_the_templates_are_todays(ruteo):
    pl = _ensamblado(ruteo)["plantillas"]
    assert set(_perfiles(pl)) == {"PerfilAgente", "PerfilJuez", "PerfilEnriquecimiento"}
    entorno, sts = _agente(pl)
    assert not {"RUTEO", "MODELO_NOVA_LITE", "MODELO_SONNET_46"} & set(entorno)
    assert len(sts["ModeloDeHaikuPorConverse"]["Resource"]) == 2
    limite = _texto(_limite(pl)["ModeloDelAgenteDelLimite"])
    assert "nova" not in limite and "sonnet" not in limite


def test_an_unknown_ruteo_stops_the_synth():
    r = _correr({"RUTEO": "r2"})
    assert r.returncode != 0 and "unknown RUTEO" in r.stderr


def test_r1_with_the_one_hour_ttl_stops_the_synth():
    r = _correr({"RUTEO": "r1", "CACHE_TTL": "1h"})
    assert r.returncode != 0 and "Nova" in r.stderr


def test_r1_without_the_application_profiles_stops_the_synth():
    r = _correr({"RUTEO": "r1"}, con_perfiles=False)
    assert r.returncode != 0 and "USAR_PERFIL_DE_APLICACION" in r.stderr


# --- r1 -------------------------------------------------------------------------------------------------------------

def test_r1_adds_one_application_profile_per_new_candidate_tagged_as_the_agent():
    perfiles = _perfiles(_ensamblado("r1")["plantillas"])
    assert set(perfiles) == {"PerfilAgente", "PerfilJuez", "PerfilEnriquecimiento", *PERFILES_NUEVOS}
    for lid, (nombre, origen) in PERFILES_NUEVOS.items():
        p = perfiles[lid]
        assert p["InferenceProfileName"] == nombre
        assert _texto(p["ModelSource"]["CopyFrom"]).endswith(f':inference-profile/{origen}"]]}}')
        etiquetas = {e["Key"]: e["Value"] for e in p["Tags"]}
        assert etiquetas["componente"] == "agente" and etiquetas["proyecto"] == "semana19"


def test_r1_passes_ruteo_and_each_candidates_profile_arn_to_the_agent():
    entorno, _ = _agente(_ensamblado("r1")["plantillas"])
    assert entorno["RUTEO"] == "r1"
    for variable, lid in (("MODELO", "PerfilAgenteInference"), ("MODELO_NOVA_LITE", "PerfilAgenteNovaLiteInference"),
                          ("MODELO_SONNET_46", "PerfilAgenteSonnet46Inference")):
        assert "Fn::ImportValue" in entorno[variable] and lid in _texto(entorno[variable]), variable


def test_r1_lets_the_agent_invoke_exactly_the_candidates():
    entorno, sts = _agente(_ensamblado("r1")["plantillas"])
    st = sts["ModeloDeHaikuPorConverse"]
    assert st["Action"] == "bedrock:InvokeModel"
    perfiles = [entorno[v] for v in ("MODELO_NOVA_LITE", "MODELO", "MODELO_SONNET_46")]
    fundacion = [f'foundation-model/{m.split(".", 1)[1]}"]]}}' for m in (NOVA, HAIKU, SONNET)]
    assert st["Resource"][:3] == perfiles
    assert len(st["Resource"]) == 6 and all(_texto(a).endswith(f) for a, f in zip(st["Resource"][3:], fundacion))
    assert "global." not in _texto(st)
    assert not [s for sid, s in sts.items() if sid != "ModeloDeHaikuPorConverse" and "bedrock:InvokeModel" in _texto(s)]


def test_r1_gives_the_boundary_the_candidates_foundation_models():
    st = _limite(_ensamblado("r1")["plantillas"])["ModeloDelAgenteDelLimite"]
    for m in (NOVA, HAIKU, SONNET):
        assert f'bedrock:*::foundation-model/{m.split(".", 1)[1]}' in _texto(st), m
    assert "application-inference-profile/*" in _texto(st)          # the candidates' profiles
    assert "inference-profile/us.amazon" not in _texto(st)           # no system profile added


def test_a_candidate_removed_from_the_configuration_leaves_the_policy():
    pl = _ensamblado("r1", "lab", (NOVA, HAIKU))["plantillas"]
    assert "PerfilAgenteSonnet46" not in _perfiles(pl)
    entorno, sts = _agente(pl)
    assert "MODELO_SONNET_46" not in entorno
    assert "sonnet" not in _texto(sts["ModeloDeHaikuPorConverse"]) and len(sts["ModeloDeHaikuPorConverse"]["Resource"]) == 4
    assert "sonnet" not in _texto(_limite(pl)["ModeloDelAgenteDelLimite"])


@pytest.mark.parametrize("perfil", ["lab", "prod"])
def test_r1_keeps_cdk_nag_at_zero(perfil):
    for pila, informe in _ensamblado("r1", perfil)["nag"].items():
        assert [r for r in informe if r["Compliance"] == "Non-Compliant"] == [], pila


@pytest.mark.parametrize("perfil", ["lab", "prod"])
def test_r1_keeps_the_boundary_under_iams_limit(perfil):
    (limite,) = [r for r in _ensamblado("r1", perfil)["plantillas"]["semana19-control"]["Resources"].values()
                 if r["Type"] == "AWS::IAM::ManagedPolicy" and r["Properties"].get("ManagedPolicyName") == "semana19-limite"]
    sys.path.insert(0, str(S19 / "tests"))
    from test_infra_cdk import _resuelto
    assert len(json.dumps(_resuelto(limite["Properties"]["PolicyDocument"]), separators=(",", ":"))) <= 6144
