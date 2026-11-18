"""Week 19, activity 7: the stack semana19-gateway, synthesis only ($0, no AWS calls). Runs in the spike-iac job.

- cdk-nag at zero findings, without suppressions; snapshots for lab and prod.
- The gateway's role may invoke the tools function and nothing else (plus evaluating its own policies and the key).
- Inbound: the pool's discovery URL, the app client, the scope legado/leer. Policy engine in ENFORCE.
- The target's tool schemas are gateway/herramientas.json; the Cedar statements are gateway/politicas/*.cedar.
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

from gateway import esquemas, politicas  # noqa: E402

PILA = "semana19-gateway"
PERFILES = ("lab", "prod")


@lru_cache(maxsize=None)
def sintetizar(perfil: str) -> dict:
    salida = Path(tempfile.mkdtemp(prefix=f"s19-gateway-{perfil}-"))
    entorno = {**os.environ, "PERFIL": perfil, "CDK_OUTDIR": str(salida), "COMPUTO": "1", "S19_SIN_DEPENDENCIAS": "1",
               "JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION": "1"}
    entorno.pop("CAMINO_HERRAMIENTAS", None)
    r = subprocess.run([sys.executable, str(APP)], env=entorno, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    plantilla = json.loads((salida / f"{PILA}.template.json").read_text(encoding="utf-8"))
    informe = list(csv.DictReader((salida / f"AwsSolutions--{PILA}-NagReport.csv").open(encoding="utf-8")))
    return {"plantilla": plantilla, "nag": informe}


def recursos(perfil: str, tipo: str) -> dict:
    return {k: r for k, r in sintetizar(perfil)["plantilla"]["Resources"].items() if r["Type"] == tipo}


def uno(perfil: str, tipo: str) -> dict:
    (r,) = recursos(perfil, tipo).values()
    return r["Properties"]


def texto(x) -> str:
    """Intrinsics as readable placeholders (imports by export name, attributes by resource)."""
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return "".join(texto(v) for v in x)
    if isinstance(x, dict):
        if "Ref" in x:
            return "{" + x["Ref"] + "}"
        if "Fn::GetAtt" in x:
            return "{" + ".".join(x["Fn::GetAtt"]) + "}"
        if "Fn::ImportValue" in x:
            return "{import:" + texto(x["Fn::ImportValue"]) + "}"
        if "Fn::Join" in x:
            return x["Fn::Join"][0].join(texto(v) for v in x["Fn::Join"][1])
    return json.dumps(x, sort_keys=True)


def declaraciones_del_rol(perfil: str) -> list[dict]:
    (rol_id,) = recursos(perfil, "AWS::IAM::Role")
    salida = []
    for r in recursos(perfil, "AWS::IAM::Policy").values():
        assert [x["Ref"] for x in r["Properties"]["Roles"]] == [rol_id]
        salida += r["Properties"]["PolicyDocument"]["Statement"]
    return salida


# ---------------------------------------------------------------- cdk-nag and snapshots

@pytest.mark.parametrize("perfil", PERFILES)
def test_cdk_nag_en_cero_sin_supresiones(perfil):
    hallazgos = [f'{r["Rule ID"]} {r["Resource ID"]}' for r in sintetizar(perfil)["nag"] if r["Compliance"] != "Compliant"]
    assert hallazgos == []
    metadatos = json.dumps([r.get("Metadata", {}) for r in sintetizar(perfil)["plantilla"]["Resources"].values()])
    assert "rules_to_suppress" not in metadatos


def _instantanea(perfil: str) -> dict:
    pl = sintetizar(perfil)["plantilla"]
    salida = {}
    for lid, r in sorted(pl["Resources"].items()):
        props = r.get("Properties", {})
        if r["Type"] == "AWS::BedrockAgentCore::Gateway":
            props = {k: props[k] for k in ("Name", "ProtocolType", "AuthorizerType", "AuthorizerConfiguration",
                                           "PolicyEngineConfiguration", "KmsKeyArn")}
        elif r["Type"] == "AWS::BedrockAgentCore::Policy":
            props = {k: props[k] for k in ("Name", "ValidationMode")}
        elif r["Type"] == "AWS::BedrockAgentCore::GatewayTarget":
            props = {"Name": props["Name"], "Credenciales": props["CredentialProviderConfigurations"],
                     "Herramientas": [t["Name"] for t in props["TargetConfiguration"]["Mcp"]["Lambda"]["ToolSchema"]["InlinePayload"]]}
        elif r["Type"] == "AWS::IAM::Role":
            props = {"AssumeRolePolicyDocument": props["AssumeRolePolicyDocument"],
                     "PermissionsBoundary": props["PermissionsBoundary"]}
        elif r["Type"] == "AWS::IAM::Policy":
            props = {"Statement": props["PolicyDocument"]["Statement"]}
        salida[lid] = {"Type": r["Type"], "Properties": json.loads(texto_profundo(props))}
    return salida


def texto_profundo(x) -> str:
    """JSON with every intrinsic replaced by its readable placeholder (stable across synths)."""
    def limpio(v):
        if isinstance(v, dict) and len(v) == 1 and next(iter(v)) in ("Ref", "Fn::GetAtt", "Fn::ImportValue", "Fn::Join"):
            return texto(v)
        if isinstance(v, dict):
            return {k: limpio(w) for k, w in v.items()}
        if isinstance(v, list):
            return [limpio(w) for w in v]
        return v
    return json.dumps(limpio(x), sort_keys=True, ensure_ascii=False)


@pytest.mark.parametrize("perfil", PERFILES)
def test_instantanea_del_gateway(perfil):
    archivo = SNAPSHOTS / f"gateway_{perfil}.json"
    actual = _instantanea(perfil)
    if os.environ.get("S19_REGENERAR") == "1":
        archivo.write_text(json.dumps(actual, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    assert actual == json.loads(archivo.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the role

@pytest.mark.parametrize("perfil", PERFILES)
def test_el_rol_del_gateway_solo_invoca_la_funcion_de_herramientas(perfil):
    sts = declaraciones_del_rol(perfil)
    lam = [s for s in sts if any(str(a).startswith("lambda:") for a in (s["Action"] if isinstance(s["Action"], list) else [s["Action"]]))]
    assert len(lam) == 1 and lam[0]["Action"] == "lambda:InvokeFunction"
    (recurso,) = [lam[0]["Resource"]] if not isinstance(lam[0]["Resource"], list) else lam[0]["Resource"]
    assert "FuncionHerramientas" in texto(recurso) and "*" not in texto(recurso)
    acciones = {a for s in sts for a in (s["Action"] if isinstance(s["Action"], list) else [s["Action"]])}
    assert acciones == {"lambda:InvokeFunction", "bedrock-agentcore:GetPolicyEngine", "bedrock-agentcore:AuthorizeAction",
                        "bedrock-agentcore:PartiallyAuthorizeActions", "kms:Decrypt", "kms:GenerateDataKey",
                        "kms:DescribeKey", "kms:CreateGrant"}
    assert all(s["Effect"] == "Allow" and "*" not in texto(s["Resource"]) for s in sts)
    (kms,) = [s for s in sts if s["Sid"] == "LlaveBaseViaAgentCore"]
    assert kms["Condition"]["StringEquals"]["kms:ViaService"] == "bedrock-agentcore.us-east-1.amazonaws.com"


@pytest.mark.parametrize("perfil", PERFILES)
def test_el_rol_lo_asume_solo_agentcore_desde_este_gateway_y_con_el_limite(perfil):
    (rol,) = recursos(perfil, "AWS::IAM::Role").values()
    (confianza,) = rol["Properties"]["AssumeRolePolicyDocument"]["Statement"]
    assert confianza["Principal"] == {"Service": "bedrock-agentcore.amazonaws.com"}
    assert texto(confianza["Condition"]["StringEquals"]["aws:SourceAccount"]) == "{AWS::AccountId}"
    assert texto(confianza["Condition"]["ArnLike"]["aws:SourceArn"]).endswith(":gateway/semana19-gateway-*")
    assert texto(rol["Properties"]["PermissionsBoundary"]).endswith(":policy/semana19-limite")


# ---------------------------------------------------------------- inbound, policy engine, target

@pytest.mark.parametrize("perfil", PERFILES)
def test_entrada_con_el_jwt_de_cognito_y_el_cliente_de_la_app(perfil):
    gw = uno(perfil, "AWS::BedrockAgentCore::Gateway")
    assert gw["AuthorizerType"] == "CUSTOM_JWT" and gw["ProtocolType"] == "MCP"
    jwt = gw["AuthorizerConfiguration"]["CustomJWTAuthorizer"]
    url = texto(jwt["DiscoveryUrl"])
    assert url.startswith("https://cognito-idp.us-east-1.amazonaws.com/{import:") and url.endswith("/.well-known/openid-configuration")
    assert "Usuarios" in url
    (cliente,) = jwt["AllowedClients"]
    assert "ClienteApp" in texto(cliente)
    assert jwt["AllowedScopes"] == ["legado/leer"] and "AllowedAudience" not in jwt
    assert "SearchType" not in json.dumps(gw)   # no semantic search: no Search-API or Tool-Indexing charges


@pytest.mark.parametrize("perfil", PERFILES)
def test_motor_de_politicas_en_enforce_y_cifrado_con_la_llave_base(perfil):
    gw = uno(perfil, "AWS::BedrockAgentCore::Gateway")
    (motor_id,) = recursos(perfil, "AWS::BedrockAgentCore::PolicyEngine")
    assert gw["PolicyEngineConfiguration"] == {"Arn": {"Fn::GetAtt": [motor_id, "PolicyEngineArn"]}, "Mode": "ENFORCE"}
    motor = uno(perfil, "AWS::BedrockAgentCore::PolicyEngine")
    assert "Llave" in texto(gw["KmsKeyArn"]) and texto(gw["KmsKeyArn"]) == texto(motor["EncryptionKeyArn"])


def _de_cfn(e: dict) -> dict:
    salida = {k: e[k] for k in ("Type", "Description", "Required") if k in e}
    salida = {k.lower(): v for k, v in salida.items()}
    if "Items" in e:
        salida["items"] = _de_cfn(e["Items"])
    if "Properties" in e:
        salida["properties"] = {n: _de_cfn(p) for n, p in e["Properties"].items()}
    return salida


@pytest.mark.parametrize("perfil", PERFILES)
def test_el_target_es_la_funcion_de_herramientas_con_los_esquemas_de_una_sola_fuente(perfil):
    t = uno(perfil, "AWS::BedrockAgentCore::GatewayTarget")
    assert t["Name"] == "herramientas"
    assert t["CredentialProviderConfigurations"] == [{"CredentialProviderType": "GATEWAY_IAM_ROLE"}]
    lam = t["TargetConfiguration"]["Mcp"]["Lambda"]
    assert "FuncionHerramientas" in texto(lam["LambdaArn"])
    cfn = [{"name": d["Name"], "description": d["Description"], "inputSchema": _de_cfn(d["InputSchema"])}
           for d in lam["ToolSchema"]["InlinePayload"]]
    assert cfn == esquemas.leer()


@pytest.mark.parametrize("perfil", PERFILES)
def test_las_politicas_son_los_archivos_cedar_con_el_arn_del_gateway(perfil):
    (gw_id,) = recursos(perfil, "AWS::BedrockAgentCore::Gateway")
    pols = {p["Properties"]["Name"]: p["Properties"] for p in recursos(perfil, "AWS::BedrockAgentCore::Policy").values()}
    assert set(pols) == set(politicas.politicas())
    for nombre, texto_cedar in politicas.politicas().items():
        p = pols[nombre]
        assert p["ValidationMode"] == "FAIL_ON_ANY_FINDINGS" and "EnforcementMode" not in p   # default ACTIVE
        sentencia = texto(p["Definition"]["Cedar"]["Statement"])
        assert sentencia == texto_cedar.replace(politicas.MARCADOR, "{" + gw_id + ".GatewayArn}")


def test_la_fuente_unica_de_esquemas_no_cambio_sin_regenerar():
    """The synth reads gateway/herramientas.json; its comparison with the loop runs in test_herramientas_formatos."""
    assert [d["name"] for d in esquemas.leer()] == ["describir_esquema", "ejecutar_sql", "proponer_orden_compra"]


def _sintetizar_computo(**extra) -> subprocess.CompletedProcess:
    salida = Path(tempfile.mkdtemp(prefix="s19-camino-"))
    entorno = {**os.environ, "PERFIL": "lab", "CDK_OUTDIR": str(salida), "COMPUTO": "1", "S19_SIN_DEPENDENCIAS": "1",
               "JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION": "1", **extra}
    r = subprocess.run([sys.executable, str(APP)], env=entorno, capture_output=True, text=True)
    r.salida = salida
    return r


def _entorno_del_agente(salida: Path) -> dict:
    pl = json.loads((salida / "semana19-computo.template.json").read_text(encoding="utf-8"))
    (agente,) = [r for k, r in pl["Resources"].items() if k.startswith("FuncionAgente") and r["Type"] == "AWS::Lambda::Function"]
    return agente["Properties"]["Environment"]["Variables"]


def test_por_omision_el_agente_va_directo_sin_url_del_gateway():
    variables = _entorno_del_agente(sintetizar_salida_lab())
    assert variables["CAMINO_HERRAMIENTAS"] == "directo" and "GATEWAY_URL" not in variables


def sintetizar_salida_lab() -> Path:
    r = _sintetizar_computo(CAMINO_HERRAMIENTAS="")
    assert r.returncode == 0, r.stderr[-2000:]
    return r.salida


@pytest.mark.parametrize("extra", [{"CAMINO_HERRAMIENTAS": "gateway"}, {"CAMINO_HERRAMIENTAS": "otro"},
                                   {"CAMINO_HERRAMIENTAS": "gateway", "S19_GATEWAY_URL": "http://x.invalid/mcp"}])
def test_un_camino_mal_configurado_no_sintetiza(extra):
    r = _sintetizar_computo(**extra)
    assert r.returncode != 0 and "CAMINO_HERRAMIENTAS" in r.stderr


def test_camino_gateway_lleva_la_url_al_agente():
    url = "https://semana19-gateway-abc.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
    r = _sintetizar_computo(CAMINO_HERRAMIENTAS="gateway", S19_GATEWAY_URL=url)
    assert r.returncode == 0, r.stderr[-2000:]
    variables = _entorno_del_agente(r.salida)
    assert variables["CAMINO_HERRAMIENTAS"] == "gateway" and variables["GATEWAY_URL"] == url


@pytest.mark.parametrize("perfil", PERFILES)
def test_el_rol_ya_evalua_el_motor_antes_de_crear_el_gateway(perfil):
    """CreateGateway checks AuthorizeAction on the engine with the role (first deploy, 2026-11-18): that statement is in
    the role's default policy, which the gateway depends on; the gateway's own ARN is added after it exists."""
    (gw_id,) = recursos(perfil, "AWS::BedrockAgentCore::Gateway")
    (motor_id,) = recursos(perfil, "AWS::BedrockAgentCore::PolicyEngine")
    pl = sintetizar(perfil)["plantilla"]["Resources"]
    (defecto_id,) = [k for k in pl if k.startswith("RolGatewayDefaultPolicy")]
    assert defecto_id in pl[gw_id]["DependsOn"]
    (motor,) = [s for s in pl[defecto_id]["Properties"]["PolicyDocument"]["Statement"] if s["Sid"] == "EvaluarSuMotorDePoliticas"]
    assert {"bedrock-agentcore:AuthorizeAction", "bedrock-agentcore:PartiallyAuthorizeActions"} <= set(motor["Action"])
    assert motor["Resource"] == {"Fn::GetAtt": [motor_id, "PolicyEngineArn"]}
    (despues,) = [k for k in pl if k.startswith("EvaluarPoliticas")]
    (st,) = pl[despues]["Properties"]["PolicyDocument"]["Statement"]
    assert st["Resource"] == {"Fn::GetAtt": [gw_id, "GatewayArn"]}
