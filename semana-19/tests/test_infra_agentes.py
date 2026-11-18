"""Week 19, activity 7: the disposable stack semana19-agentes-comparacion (path c), synthesis only ($0, no AWS calls).
Runs in the spike-iac job. cdk-nag at zero without suppressions; snapshots for lab and prod.
"""
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
SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"
sys.path.insert(0, str(S19))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gateway import esquemas  # noqa: E402
from ia.config import MODELO_ID, NOMBRE_EMPRESA  # noqa: E402
from ia.peticion import renderizar  # noqa: E402
from test_infra_gateway import texto, texto_profundo  # noqa: E402

PILA = "semana19-agentes-comparacion"
PERFILES = ("lab", "prod")


@lru_cache(maxsize=None)
def sintetizar(perfil: str) -> dict:
    salida = Path(tempfile.mkdtemp(prefix=f"s19-agentes-{perfil}-"))
    entorno = {**os.environ, "PERFIL": perfil, "CDK_OUTDIR": str(salida), "COMPUTO": "1", "S19_SIN_DEPENDENCIAS": "1",
               "JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION": "1"}
    entorno.pop("CAMINO_HERRAMIENTAS", None)
    r = subprocess.run([sys.executable, str(APP)], env=entorno, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    leer = lambda n: json.loads((salida / f"{n}.template.json").read_text(encoding="utf-8"))  # noqa: E731
    return {"plantilla": leer(PILA), "ia": leer("semana19-ia"),
            "nag": list(csv.DictReader((salida / f"AwsSolutions--{PILA}-NagReport.csv").open(encoding="utf-8")))}


def recursos(perfil: str, tipo: str, plantilla: str = "plantilla") -> dict:
    return {k: r for k, r in sintetizar(perfil)[plantilla]["Resources"].items() if r["Type"] == tipo}


def uno(perfil: str, tipo: str) -> dict:
    (r,) = recursos(perfil, tipo).values()
    return r["Properties"]


def lista(x):
    return x if isinstance(x, list) else [x]


@pytest.mark.parametrize("perfil", PERFILES)
def test_cdk_nag_en_cero_sin_supresiones(perfil):
    assert [f'{r["Rule ID"]} {r["Resource ID"]}' for r in sintetizar(perfil)["nag"] if r["Compliance"] != "Compliant"] == []
    assert "rules_to_suppress" not in json.dumps(sintetizar(perfil)["plantilla"])


def _instantanea(perfil: str) -> dict:
    salida = {}
    for lid, r in sorted(sintetizar(perfil)["plantilla"]["Resources"].items()):
        props = dict(r.get("Properties", {}))
        if r["Type"] == "AWS::Bedrock::Agent":
            props["Instruction"] = f"<{len(props['Instruction'])} caracteres>"
        if r["Type"] == "AWS::IAM::Policy":
            props = {"Statement": props["PolicyDocument"]["Statement"]}
        salida[lid] = {"Type": r["Type"], "Properties": json.loads(texto_profundo(props))}
    return salida


@pytest.mark.parametrize("perfil", PERFILES)
def test_instantanea_de_la_comparacion(perfil):
    archivo = SNAPSHOTS / f"agentes_{perfil}.json"
    actual = _instantanea(perfil)
    if os.environ.get("S19_REGENERAR") == "1":
        archivo.write_text(json.dumps(actual, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    assert actual == json.loads(archivo.read_text(encoding="utf-8"))


@pytest.mark.parametrize("perfil", PERFILES)
def test_la_instruccion_es_el_prompt_de_la_version_fijada(perfil):
    """The same text semana19-ia publishes as the pinned Spanish version, rendered with the company."""
    (prompt,) = [r["Properties"] for r in recursos(perfil, "AWS::Bedrock::Prompt", "ia").values()
                 if r["Properties"]["Name"] == "semana19-sistema-es"]
    (variante,) = prompt["Variants"]
    publicado = variante["TemplateConfiguration"]["Text"]["Text"]
    (version,) = [r["Properties"] for r in recursos(perfil, "AWS::Bedrock::PromptVersion", "ia").values()
                  if "es" in r["Properties"]["Description"].split()[-1]]
    assert version["PromptArn"]["Fn::GetAtt"][1] == "Arn"
    agente = uno(perfil, "AWS::Bedrock::Agent")
    assert agente["Instruction"] == renderizar(publicado, {"nombre_empresa": NOMBRE_EMPRESA["es"]})
    assert "{{" not in agente["Instruction"]


@pytest.mark.parametrize("perfil", PERFILES)
def test_modelo_guardrail_de_version_fija_preparado_y_con_alias(perfil):
    a = uno(perfil, "AWS::Bedrock::Agent")
    assert a["FoundationModel"] == MODELO_ID and a["AutoPrepare"] is True
    g = a["GuardrailConfiguration"]
    assert "GuardrailId" in texto(g["GuardrailIdentifier"]) and "GuardrailVersion" in texto(g["GuardrailVersion"])
    assert texto(g["GuardrailIdentifier"]).startswith("{import:semana19-ia:")
    assert "Llave" in texto(a["CustomerEncryptionKeyArn"])
    (agente_id,) = recursos(perfil, "AWS::Bedrock::Agent")
    assert uno(perfil, "AWS::Bedrock::AgentAlias")["AgentId"] == {"Fn::GetAtt": [agente_id, "AgentId"]}


@pytest.mark.parametrize("perfil", PERFILES)
def test_el_ejecutor_es_la_funcion_de_herramientas_con_las_mismas_herramientas(perfil):
    (grupo,) = uno(perfil, "AWS::Bedrock::Agent")["ActionGroups"]
    assert grupo["ActionGroupName"] == "herramientas"
    assert "FuncionHerramientas" in texto(grupo["ActionGroupExecutor"]["Lambda"])
    funciones = {f["Name"]: f for f in grupo["FunctionSchema"]["Functions"]}
    fuente = {d["name"]: d["inputSchema"] for d in esquemas.leer()}
    assert set(funciones) == set(fuente)
    for nombre, esquema in fuente.items():
        params = funciones[nombre].get("Parameters", {})
        esperados = {n: e for n, e in esquema.get("properties", {}).items() if n != "solicitante"}
        assert {n: p["Type"] for n, p in params.items()} == {n: e["type"] for n, e in esperados.items()}
        assert {n for n, p in params.items() if p["Required"]} == set(esquema.get("required", [])) - {"solicitante"}
    assert "solicitante" not in json.dumps(grupo)   # on this path the requester comes from the session attributes


@pytest.mark.parametrize("perfil", PERFILES)
def test_el_rol_solo_usa_el_modelo_el_guardrail_y_la_llave(perfil):
    (rol,) = recursos(perfil, "AWS::IAM::Role").values()
    (confianza,) = rol["Properties"]["AssumeRolePolicyDocument"]["Statement"]
    assert confianza["Principal"] == {"Service": "bedrock.amazonaws.com"}
    assert texto(confianza["Condition"]["StringEquals"]["aws:SourceAccount"]) == "{AWS::AccountId}"
    assert texto(confianza["Condition"]["ArnLike"]["aws:SourceArn"]).endswith(":agent/*")
    assert texto(rol["Properties"]["PermissionsBoundary"]).endswith(":policy/semana19-limite")
    (pol,) = recursos(perfil, "AWS::IAM::Policy").values()
    sts = pol["Properties"]["PolicyDocument"]["Statement"]
    acciones = {a for s in sts for a in lista(s["Action"])}
    assert acciones == {"bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:GetInferenceProfile",
                        "bedrock:GetFoundationModel", "bedrock:ApplyGuardrail", "kms:Decrypt", "kms:GenerateDataKey",
                        "kms:DescribeKey"}
    assert not any(a.startswith("lambda:") for a in acciones)   # the function is reached by its resource policy
    for s in sts:
        assert "*" not in texto(s["Resource"])
    (modelo,) = [s for s in sts if s["Sid"] == "ModeloDelAgente"]
    destinos = [texto(r) for r in lista(modelo["Resource"])]
    assert any(d.endswith(f"inference-profile/{MODELO_ID}") for d in destinos)
    assert all("foundation-model/" + MODELO_ID.split(".", 1)[1] in d for d in destinos if "foundation-model" in d)


@pytest.mark.parametrize("perfil", PERFILES)
def test_la_funcion_solo_la_invoca_este_agente(perfil):
    p = uno(perfil, "AWS::Lambda::Permission")
    (agente_id,) = recursos(perfil, "AWS::Bedrock::Agent")
    assert p["Action"] == "lambda:InvokeFunction" and p["Principal"] == "bedrock.amazonaws.com"
    assert p["SourceArn"] == {"Fn::GetAtt": [agente_id, "AgentArn"]} and p["SourceAccount"] == {"Ref": "AWS::AccountId"}
    assert "FuncionHerramientas" in texto(p["FunctionName"])
