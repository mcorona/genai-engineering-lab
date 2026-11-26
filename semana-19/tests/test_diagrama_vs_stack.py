"""Week 19, activity 10: the architecture diagram matches the synthesized stacks, both ways (no AWS calls).

- Every node of `arquitectura/diagrama.mmd` maps to resources in the synth (by CloudFormation type and logical-ID
  prefix), or is listed as having no resource of its own (the client, the Bedrock runtime call).
- Every component of the synth (a Lambda function, a data store, an endpoint, a Bedrock or AgentCore resource...) is
  drawn, or is listed as out of the diagram with a reason.

A new node without a mapping, a mapped resource that is gone, or a new component nobody drew fails the test.
Needs aws-cdk-lib (spike-iac job)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
APP = S19 / "infra" / "cdk" / "app.py"
DIAGRAMA = S19 / "arquitectura" / "diagrama.mmd"

# Diagram node -> the (stack, type, logical-ID prefix) resources that realize it.
NODOS = {
    "cognito": [("semana19-computo", "AWS::Cognito::UserPool", "Usuarios")],
    "pretoken": [("semana19-computo", "AWS::Lambda::Function", "FuncionTokens")],
    "apigw": [("semana19-computo", "AWS::ApiGatewayV2::Api", "Api"),
              ("semana19-computo", "AWS::ApiGatewayV2::Authorizer", "")],
    "consultas": [("semana19-computo", "AWS::Lambda::Function", "FuncionConsultas")],
    "tconsultas": [("semana19-computo", "AWS::DynamoDB::Table", "Consultas")],
    "agente": [("semana19-computo", "AWS::Lambda::Function", "FuncionAgente")],
    "aprobar": [("semana19-computo", "AWS::Lambda::Function", "FuncionAprobar")],
    "registrar": [("semana19-computo", "AWS::Lambda::Function", "FuncionRegistrarToken")],
    "ttokens": [("semana19-computo", "AWS::DynamoDB::Table", "Tokens")],
    "sfn": [("semana19-computo", "AWS::StepFunctions::StateMachine", "Aprobacion")],
    "converse": [("semana19-ia", "AWS::CloudFormation::CustomResource", "Guardrail"),
                 ("semana19-ia", "AWS::Bedrock::Prompt", "PromptES"),
                 ("semana19-ia", "AWS::Bedrock::Prompt", "PromptEN")],
    "gw": [("semana19-gateway", "AWS::BedrockAgentCore::Gateway", "Gateway"),
           ("semana19-gateway", "AWS::BedrockAgentCore::PolicyEngine", "")],
    "tools": [("semana19-computo", "AWS::Lambda::Function", "FuncionHerramientas")],
    "escritor": [("semana19-computo", "AWS::Lambda::Function", "FuncionEscritor")],
    "cargador": [("semana19-datos", "AWS::Lambda::Function", "Cargador")],
    "rds": [("semana19-datos", "AWS::RDS::DBInstance", "PostgreSQL")],
    "ep": [("semana19-base", "AWS::EC2::VPCEndpoint", "EndpointS3"),
           ("semana19-base", "AWS::EC2::VPCEndpoint", "EndpointLogs"),
           ("semana19-base", "AWS::EC2::VPCEndpoint", "EndpointStepFunctions"),
           ("semana19-datos", "AWS::EC2::VPCEndpoint", "EndpointSecretos")],
    "docs": [("semana19-datos", "AWS::S3::Bucket", "DocsKb")],
    "kb": [("semana19-datos", "AWS::Bedrock::KnowledgeBase", "KbLegado"),
           ("semana19-datos", "AWS::S3Vectors::VectorBucket", "VectoresKb")],
    "cw": [("semana19-base", "AWS::EC2::FlowLog", ""), ("semana19-computo", "AWS::Logs::LogGroup", "")],
    "kms": [("semana19-base", "AWS::KMS::Key", "Llave")],
}
SIN_RECURSO = {"cliente": "the user, outside AWS"}

# The component types checked the other way, and the components left out of the diagram on purpose.
COMPONENTES = {"AWS::Lambda::Function", "AWS::DynamoDB::Table", "AWS::S3::Bucket", "AWS::RDS::DBInstance",
               "AWS::StepFunctions::StateMachine", "AWS::EC2::VPCEndpoint", "AWS::Cognito::UserPool",
               "AWS::ApiGatewayV2::Api", "AWS::Bedrock::KnowledgeBase", "AWS::Bedrock::Prompt",
               "AWS::Bedrock::Agent", "AWS::BedrockAgentCore::Gateway", "AWS::S3Vectors::VectorBucket",
               "AWS::KMS::Key", "AWS::CloudFormation::CustomResource"}
# Every other type of the synth, and why the diagram does not draw it. A type in none of the three lists fails.
TIPOS_IGNORADOS = {
    "AWS::IAM::Role": "identities, not components; the boundary and least privilege are in the threat model",
    "AWS::IAM::Policy": "permissions of the roles above",
    "AWS::IAM::ManagedPolicy": "the permissions boundary, the freeze policy and the CloudFormation execution policies",
    "AWS::EC2::VPC": "drawn as the F9 box",
    "AWS::EC2::Subnet": "inside the F9 box (isolated subnets)",
    "AWS::EC2::RouteTable": "inside the F9 box",
    "AWS::EC2::SubnetRouteTableAssociation": "inside the F9 box",
    "AWS::EC2::SecurityGroup": "network rules between the boxes, in seguridad/threat_model.md",
    "AWS::EC2::SecurityGroupIngress": "network rules between the boxes",
    "AWS::EC2::SecurityGroupEgress": "network rules between the boxes",
    "AWS::Lambda::Permission": "the edges into a Lambda (API Gateway, the gateway)",
    "AWS::Lambda::EventInvokeConfig": "the async invoke with no retries, drawn on the edge consultas -> agente",
    "AWS::ApiGatewayV2::Integration": "the edges from the API to its Lambdas",
    "AWS::ApiGatewayV2::Route": "the scopes on those edges",
    "AWS::ApiGatewayV2::Stage": "part of the API node",
    "AWS::Cognito::UserPoolClient": "part of the Cognito node",
    "AWS::Cognito::UserPoolGroup": "the groups of the Cognito node",
    "AWS::Cognito::UserPoolResourceServer": "the scopes of the Cognito node",
    "AWS::RDS::DBSubnetGroup": "part of the RDS node",
    "AWS::SecretsManager::Secret": "the database master secret, reached through the Secrets Manager endpoint",
    "AWS::SecretsManager::SecretTargetAttachment": "part of that secret",
    "AWS::S3::BucketPolicy": "part of each bucket",
    "AWS::S3Vectors::Index": "part of the KB's vector bucket",
    "AWS::Bedrock::DataSource": "the edge docs -> kb",
    "AWS::Bedrock::PromptVersion": "the fixed prompt version of the converse node",
    "AWS::Bedrock::ApplicationInferenceProfile": "week 20: the cost tag on the converse node's model call (no new flow)",
    "AWS::Bedrock::AgentAlias": "part of activity 7's comparison agent, out of the diagram",
    "AWS::BedrockAgentCore::GatewayTarget": "the edge gw -> tools",
    "AWS::BedrockAgentCore::Policy": "the Cedar policies of the gateway node",
    "AWS::KMS::Alias": "part of the KMS node",
    "AWS::Budgets::Budget": "a control-plane spend control (F11 is a flow, not a box)",
    "AWS::Budgets::BudgetsAction": "the budget's action on the deploy role (F11)",
    "Custom::VpcRestrictDefaultSG": "CDK closes the default security group of the VPC",
}

FUERA = {
    ("semana19-agentes-comparacion", "Agente"): "activity 7's Bedrock Agents comparison, destroyed after it",
    ("semana19-eval", "Juez"): "activity 8's judge bucket for Bedrock model evaluation, destroyed after it",
    ("semana19-ia", "CreadorGuardrail"): "the Lambda behind the Guardrail custom resource (node converse)",
    ("semana19-base", "CustomVpcRestrictDefaultSG"): "CDK's handler that closes the default security group",
}


@lru_cache(maxsize=1)
def plantillas() -> dict[str, dict]:
    salida = Path(tempfile.mkdtemp(prefix="s19-diagrama-"))
    entorno = {**os.environ, "PERFIL": "lab", "CDK_OUTDIR": str(salida), "COMPUTO": "1", "S19_SIN_DEPENDENCIAS": "1",
               "JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION": "1"}
    for v in ("CAMINO_HERRAMIENTAS", "S19_GATEWAY_FASE", "S19_GATEWAY_URL"):
        entorno.pop(v, None)
    r = subprocess.run([sys.executable, str(APP)], env=entorno, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    return {f.name.removesuffix(".template.json"): json.loads(f.read_text(encoding="utf-8"))
            for f in salida.glob("semana19-*.template.json")}


def nodos_del_diagrama(texto: str) -> set[str]:
    """Node ids: a word followed by a shape opener, outside comments and subgraph headers."""
    ids = set()
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("%%") or linea.startswith(("subgraph", "flowchart", "end")):
            continue
        ids.update(re.findall(r"(?:^|[\s>|])([a-z][a-z0-9_]*)\s*(?=[\[\(\{])", linea))
    return ids


def _existe(stack: str, tipo: str, prefijo: str) -> bool:
    recursos = plantillas().get(stack, {}).get("Resources", {})
    return any(r["Type"] == tipo and k.startswith(prefijo) for k, r in recursos.items())


def test_cada_nodo_del_diagrama_tiene_su_mapeo():
    nodos = nodos_del_diagrama(DIAGRAMA.read_text(encoding="utf-8"))
    assert nodos == set(NODOS) | set(SIN_RECURSO), {"sin_mapeo": nodos - set(NODOS) - set(SIN_RECURSO),
                                                    "mapeo_sin_nodo": (set(NODOS) | set(SIN_RECURSO)) - nodos}


def test_cada_nodo_mapeado_existe_en_el_synth():
    faltan = [(n, s, t, p) for n, rs in NODOS.items() for s, t, p in rs if not _existe(s, t, p)]
    assert not faltan, faltan


def test_cada_componente_del_synth_esta_dibujado_o_excluido_con_motivo():
    dibujados = {(s, p) for rs in NODOS.values() for s, t, p in rs if p}
    sin_dibujar = []
    for stack, plantilla in plantillas().items():
        for k, r in plantilla.get("Resources", {}).items():
            if r["Type"] not in COMPONENTES:
                continue
            if any(stack == s and k.startswith(p) for s, p in dibujados | set(FUERA)):
                continue
            sin_dibujar.append((stack, r["Type"], k))
    assert not sin_dibujar, sin_dibujar


def test_el_lector_del_diagrama_reconoce_las_formas():
    texto = 'a[x]\n  b([y]) --> c[(z)]\n  d{{k}}\n  e[[s]]\n  %% f[no]\n  subgraph G["t"]\n  a -->|"p"| b'
    assert nodos_del_diagrama(texto) == {"a", "b", "c", "d", "e"}


def test_cada_tipo_del_synth_esta_dibujado_revisado_o_ignorado_con_motivo():
    mapeados = {t for rs in NODOS.values() for _, t, _ in rs}
    tipos = {r["Type"] for p in plantillas().values() for r in p.get("Resources", {}).values()}
    sin_revisar = tipos - COMPONENTES - mapeados - set(TIPOS_IGNORADOS)
    assert not sin_revisar, sin_revisar
    assert not (set(TIPOS_IGNORADOS) & (COMPONENTES | mapeados)), "a type cannot be both drawn and ignored"
