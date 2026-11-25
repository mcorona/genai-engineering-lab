"""Week 19, activity 9, step 1: IAM Access Analyzer `ValidatePolicy` on every policy document of the synth.

    uv run --group semana19 python semana-19/seguridad/validar_politicas.py --synth lab=<dir> --synth prod=<dir> \
        [--perfil semana19-lectura] [--salida semana-19/resultados/seguridad/validate_policy.json] [--simular]

Policy validation is free (IAM Access Analyzer pricing: "provided at no additional charge") and read-only: it creates
nothing. It runs with the read-only role semana19-lectura (ReadOnlyAccess allows access-analyzer:ValidatePolicy).
`--simular` lists the documents and makes no call.

Documents, from every template of the synth (all stacks, COMPUTO=1):

| Resource | Field | policyType | validatePolicyResourceType |
|---|---|---|---|
| AWS::IAM::Policy, AWS::IAM::ManagedPolicy (boundary and freeze policy included) | PolicyDocument | IDENTITY_POLICY | - |
| AWS::IAM::Role | Policies[].PolicyDocument | IDENTITY_POLICY | - |
| AWS::IAM::Role | AssumeRolePolicyDocument | RESOURCE_POLICY | AWS::IAM::AssumeRolePolicyDocument |
| AWS::S3::BucketPolicy | PolicyDocument | RESOURCE_POLICY | AWS::S3::Bucket |
| AWS::KMS::Key | KeyPolicy | RESOURCE_POLICY | - (no KMS type in the API) |
| AWS::EC2::VPCEndpoint | PolicyDocument | RESOURCE_POLICY | - |
| AWS::Logs::ResourcePolicy, AWS::SQS::QueuePolicy, AWS::SNS::TopicPolicy | PolicyDocument | RESOURCE_POLICY | - |

CloudFormation intrinsics are resolved to example values of the right shape before the call: the documentation
account 111122223333, us-east-1, partition aws, and ARNs built from each resource's type and name. Cross-stack
imports are resolved through the exports of the other templates. An intrinsic the resolver does not know stops the
run, so no document is validated half-resolved.

The snapshot keeps, per document, its SHA-256 (of the template's document, before resolution) and its findings.
`tests/test_validar_politicas.py` fails if the snapshot has an ERROR or a SECURITY_WARNING, and the coverage test
fails if a document of the current synth is not in the snapshot. The one exception is `RECHAZOS_DESMENTIDOS`: an
INVALID_ACTION that a live deploy showed IAM does evaluate. It stays in the snapshot, marked with its evidence, and is
not counted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))
from comun.redaccion import redactar  # noqa: E402

SALIDA = S19 / "resultados" / "seguridad" / "validate_policy.json"
CUENTA, REGION, PARTICION = "111122223333", "us-east-1", "aws"
LLAVE_EJEMPLO = "1234abcd-12ab-34cd-56ef-1234567890ab"
MALAS = {"ERROR", "SECURITY_WARNING"}

# INVALID_ACTION findings that a live deploy disproved: IAM evaluates these actions, so removing them breaks the deploy.
# Activity 9 removed both after ValidatePolicy reported "The action ... does not exist." (#298); on 2026-11-21 the
# AWS::ApiGatewayV2::Stage handler of semana19-computo then failed with AccessDenied, naming apigateway:TagResource.
RECHAZOS_DESMENTIDOS = {
    a: "IAM evaluated it on 2026-11-21: CloudFormation's AWS::ApiGatewayV2::Stage handler was denied "
       "apigateway:TagResource while creating semana19-computo (activity 9, step 4.1)"
    for a in ("apigateway:TagResource", "apigateway:UntagResource")}
_ACCION_INEXISTENTE = re.compile(r"^The action (\S+) does not exist\.$")


def desmentido(h: dict) -> str | None:
    """The evidence that disproves this finding, or None if the finding stands."""
    m = _ACCION_INEXISTENTE.match(h.get("detalle", ""))
    if h.get("issueCode") != "INVALID_ACTION" or not m:
        return None
    return RECHAZOS_DESMENTIDOS.get(m.group(1))

PSEUDO = {"AWS::Partition": PARTICION, "AWS::AccountId": CUENTA, "AWS::Region": REGION,
          "AWS::URLSuffix": "amazonaws.com", "AWS::NoValue": None}

# (resource type, field) -> (policyType, validatePolicyResourceType or None)
CAMPOS = {
    ("AWS::IAM::Policy", "PolicyDocument"): ("IDENTITY_POLICY", None),
    ("AWS::IAM::ManagedPolicy", "PolicyDocument"): ("IDENTITY_POLICY", None),
    ("AWS::IAM::Role", "AssumeRolePolicyDocument"): ("RESOURCE_POLICY", "AWS::IAM::AssumeRolePolicyDocument"),
    ("AWS::S3::BucketPolicy", "PolicyDocument"): ("RESOURCE_POLICY", "AWS::S3::Bucket"),
    ("AWS::KMS::Key", "KeyPolicy"): ("RESOURCE_POLICY", None),
    ("AWS::EC2::VPCEndpoint", "PolicyDocument"): ("RESOURCE_POLICY", None),
    ("AWS::Logs::ResourcePolicy", "PolicyDocument"): ("RESOURCE_POLICY", None),
    ("AWS::SQS::QueuePolicy", "PolicyDocument"): ("RESOURCE_POLICY", None),
    ("AWS::SNS::TopicPolicy", "PolicyDocument"): ("RESOURCE_POLICY", None),
}

# The name property of each type, when the template sets one.
PROPIEDAD_NOMBRE = {"AWS::IAM::Role": "RoleName", "AWS::IAM::ManagedPolicy": "ManagedPolicyName",
                    "AWS::S3::Bucket": "BucketName", "AWS::Lambda::Function": "FunctionName",
                    "AWS::DynamoDB::Table": "TableName", "AWS::Logs::LogGroup": "LogGroupName",
                    "AWS::StepFunctions::StateMachine": "StateMachineName", "AWS::SecretsManager::Secret": "Name"}


class SinResolver(Exception):
    pass


class Resolutor:
    """Resolves intrinsics of one template; imports go through the exports of the whole synth."""

    def __init__(self, plantillas: dict[str, dict]):
        self.plantillas = plantillas
        self.exportes: dict[str, tuple[str, object]] = {}
        for pila, t in plantillas.items():
            for salida in t.get("Outputs", {}).values():
                if "Export" in salida and isinstance(salida["Export"].get("Name"), str):
                    self.exportes[salida["Export"]["Name"]] = (pila, salida["Value"])

    def nombre(self, pila: str, logico: str) -> str:
        r = self.plantillas[pila]["Resources"][logico]
        prop = PROPIEDAD_NOMBRE.get(r["Type"])
        valor = r.get("Properties", {}).get(prop) if prop else None
        if valor is not None:
            return str(self.resolver(pila, valor))
        return re.sub(r"[^a-z0-9-]", "-", f"{pila}-{logico}".lower())[:63]

    def arn(self, pila: str, logico: str) -> str:
        tipo = self.plantillas[pila]["Resources"][logico]["Type"]
        n = self.nombre(pila, logico)
        p, c, r = PARTICION, CUENTA, REGION
        formatos = {
            "AWS::IAM::Role": f"arn:{p}:iam::{c}:role/{n}",
            "AWS::IAM::ManagedPolicy": f"arn:{p}:iam::{c}:policy/{n}",
            "AWS::S3::Bucket": f"arn:{p}:s3:::{n}",
            "AWS::Lambda::Function": f"arn:{p}:lambda:{r}:{c}:function:{n}",
            "AWS::DynamoDB::Table": f"arn:{p}:dynamodb:{r}:{c}:table/{n}",
            "AWS::Logs::LogGroup": f"arn:{p}:logs:{r}:{c}:log-group:{n}:*",
            "AWS::KMS::Key": f"arn:{p}:kms:{r}:{c}:key/{LLAVE_EJEMPLO}",
            "AWS::StepFunctions::StateMachine": f"arn:{p}:states:{r}:{c}:stateMachine:{n}",
            "AWS::SecretsManager::Secret": f"arn:{p}:secretsmanager:{r}:{c}:secret:{n}-AbCdEf",
            "AWS::SecretsManager::SecretTargetAttachment": f"arn:{p}:secretsmanager:{r}:{c}:secret:{n}-AbCdEf",
            "AWS::Bedrock::KnowledgeBase": f"arn:{p}:bedrock:{r}:{c}:knowledge-base/KBEXAMPLE1",
            "AWS::S3Vectors::Index": f"arn:{p}:s3vectors:{r}:{c}:bucket/{n}/index/{n}",
            "AWS::S3Vectors::VectorBucket": f"arn:{p}:s3vectors:{r}:{c}:bucket/{n}",
            "AWS::BedrockAgentCore::Gateway": f"arn:{p}:bedrock-agentcore:{r}:{c}:gateway/{n}-abcdefghij",
            "AWS::BedrockAgentCore::PolicyEngine": f"arn:{p}:bedrock-agentcore:{r}:{c}:policy-engine/{n}-abcdefghij",
            "AWS::Bedrock::Guardrail": f"arn:{p}:bedrock:{r}:{c}:guardrail/gexample01",
            "AWS::Bedrock::ApplicationInferenceProfile": f"arn:{p}:bedrock:{r}:{c}:application-inference-profile/aipexample01",
            "AWS::SQS::Queue": f"arn:{p}:sqs:{r}:{c}:{n}",
            "AWS::SNS::Topic": f"arn:{p}:sns:{r}:{c}:{n}",
        }
        if tipo not in formatos:
            raise SinResolver(f"{pila}: no ARN format for {tipo} ({logico})")
        return formatos[tipo]

    def ref(self, pila: str, nombre: str):
        if nombre in PSEUDO:
            return PSEUDO[nombre]
        if nombre == "AWS::StackName":
            return pila
        t = self.plantillas[pila]
        if nombre in t.get("Parameters", {}):
            par = t["Parameters"][nombre]
            if "Default" not in par:
                raise SinResolver(f"{pila}: parameter {nombre} has no default")
            return par["Default"]
        tipo = t["Resources"][nombre]["Type"]
        if tipo in ("AWS::StepFunctions::StateMachine", "AWS::SecretsManager::SecretTargetAttachment",
                    "AWS::SecretsManager::Secret", "AWS::IAM::ManagedPolicy", "AWS::SNS::Topic"):
            return self.arn(pila, nombre)
        if tipo == "AWS::KMS::Key":
            return LLAVE_EJEMPLO
        return self.nombre(pila, nombre)

    def getatt(self, pila: str, logico: str, atributo: str):
        tipo = self.plantillas[pila]["Resources"][logico]["Type"]
        if atributo in ("Arn", "GatewayArn", "PolicyEngineArn", "KnowledgeBaseArn", "IndexArn", "VectorBucketArn",
                        "InferenceProfileArn"):
            return self.arn(pila, logico)
        fijos = {"GroupId": "sg-0123456789abcdef0", "DefaultSecurityGroup": "sg-0fedcba9876543210",
                 "DbiResourceId": "db-ABCDEFGHIJKLMNOPQRSTUVWXY0", "Endpoint.Address": "db.example.us-east-1.rds.amazonaws.com",
                 "KeyId": LLAVE_EJEMPLO, "GuardrailId": "gexample01", "Version": "1", "KnowledgeBaseId": "KBEXAMPLE1"}
        if atributo in fijos:
            return fijos[atributo]
        raise SinResolver(f"{pila}: no value for GetAtt {tipo}.{atributo} ({logico})")

    def resolver(self, pila: str, x):
        if isinstance(x, list):
            return [v for v in (self.resolver(pila, i) for i in x) if v is not None]
        if not isinstance(x, dict):
            return x
        if len(x) == 1:
            (k, v), = x.items()
            if k == "Ref":
                return self.ref(pila, v)
            if k == "Fn::GetAtt":
                logico, atributo = (v.split(".", 1) if isinstance(v, str) else v)
                return self.getatt(pila, logico, atributo)
            if k == "Fn::Join":
                sep, partes = v
                return sep.join(str(p) for p in self.resolver(pila, partes))
            if k == "Fn::Sub":
                plantilla, variables = (v, {}) if isinstance(v, str) else (v[0], v[1])
                def sustituir(m):
                    nombre = m.group(1)
                    if nombre in variables:
                        return str(self.resolver(pila, variables[nombre]))
                    if "." in nombre:
                        return str(self.getatt(pila, *nombre.split(".", 1)))
                    return str(self.ref(pila, nombre))
                return re.sub(r"\$\{([^}!]+)\}", sustituir, plantilla)
            if k == "Fn::ImportValue":
                nombre = self.resolver(pila, v)
                if nombre not in self.exportes:
                    raise SinResolver(f"{pila}: import {nombre} has no export in the synth")
                origen, valor = self.exportes[nombre]
                return self.resolver(origen, valor)
            if k == "Fn::Select":
                indice, lista = v
                return self.resolver(pila, lista)[int(indice)]
            if k.startswith("Fn::"):
                raise SinResolver(f"{pila}: intrinsic {k} not supported")
        return {k: self.resolver(pila, v) for k, v in x.items()}


def huella(doc) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def documentos(carpeta: Path) -> list[dict]:
    """Every policy document of the synth, resolved, with its type for ValidatePolicy."""
    plantillas = {f.name.removesuffix(".template.json"): json.loads(f.read_text(encoding="utf-8"))
                  for f in sorted(carpeta.glob("*.template.json"))}
    if not plantillas:
        raise SystemExit(f"{carpeta}: no templates; synthesize every stack with COMPUTO=1 first")
    res = Resolutor(plantillas)
    salida = []
    for pila, t in plantillas.items():
        for logico, r in t.get("Resources", {}).items():
            props = r.get("Properties", {})
            entradas = [(campo, props[campo]) for (tipo, campo) in CAMPOS if tipo == r["Type"] and campo in props]
            if r["Type"] == "AWS::IAM::Role":
                entradas += [(f"Policies[{i}]", p["PolicyDocument"]) for i, p in enumerate(props.get("Policies", []))
                             if isinstance(p, dict) and "PolicyDocument" in p]
            for campo, doc in entradas:
                clave = "PolicyDocument" if campo.startswith("Policies[") else campo
                tipo_politica, tipo_recurso = CAMPOS.get((r["Type"], clave), ("IDENTITY_POLICY", None))
                resuelto = res.resolver(pila, doc)
                if isinstance(resuelto, str):
                    resuelto = json.loads(resuelto)
                salida.append({"stack": pila, "recurso": logico, "tipo": r["Type"], "campo": campo,
                               "policyType": tipo_politica, "validatePolicyResourceType": tipo_recurso,
                               "huella": huella(doc), "documento": resuelto})
    return salida


def validar(cliente, doc: dict) -> list[dict]:
    params = {"policyDocument": json.dumps(doc["documento"]), "policyType": doc["policyType"]}
    if doc["validatePolicyResourceType"]:
        params["validatePolicyResourceType"] = doc["validatePolicyResourceType"]
    hallazgos = []
    for pagina in cliente.get_paginator("validate_policy").paginate(**params):
        for f in pagina["findings"]:
            hallazgos.append({"findingType": f["findingType"], "issueCode": f["issueCode"],
                              "detalle": f["findingDetails"], "learnMoreLink": f.get("learnMoreLink"),
                              "ruta": [list(p.values())[0] for loc in f.get("locations", [])[:1] for p in loc["path"]]})
    return hallazgos


def informe(perfiles: dict[str, list[dict]]) -> dict:
    total = Counter()
    malos = desmentidos = 0
    for docs in perfiles.values():
        for d in docs:
            for h in d["hallazgos"]:
                total[h["findingType"]] += 1
                if motivo := desmentido(h):
                    h["desmentido"] = motivo
                    desmentidos += 1
                elif h["findingType"] in MALAS:
                    malos += 1
    return redactar({
        "herramienta": "IAM Access Analyzer ValidatePolicy (policy validation, no charge)",
        "valores_de_ejemplo": {"cuenta": CUENTA, "region": REGION, "particion": PARTICION},
        "por_perfil": {p: {"documentos": len(docs),
                           "por_tipo": dict(sorted(Counter(d["policyType"] for d in docs).items())),
                           "hallazgos": dict(sorted(Counter(h["findingType"] for d in docs for h in d["hallazgos"]).items()))}
                       for p, docs in perfiles.items()},
        "hallazgos_por_tipo": dict(sorted(total.items())), "errores_o_advertencias_de_seguridad": malos,
        "desmentidos_por_un_despliegue": desmentidos,
        "veredicto": "ok" if malos == 0 else "revisar",
        "documentos": {p: [{k: v for k, v in d.items() if k != "documento"} for d in docs]
                       for p, docs in perfiles.items()}}, cuentas=[CUENTA])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--synth", action="append", required=True, metavar="PERFIL=DIR")
    ap.add_argument("--perfil", "--profile", default="semana19-lectura", help="read-only AWS profile", metavar="PROFILE")
    ap.add_argument("--salida", "--output", type=Path, default=SALIDA, metavar="OUTPUT")
    ap.add_argument("--simular", "--simulate", action="store_true", help="list the documents, no call")
    a = ap.parse_args(argv)
    por_perfil = {p: documentos(Path(c)) for p, _, c in (s.partition("=") for s in a.synth)}
    if a.simular:
        for p, docs in por_perfil.items():
            print(p, len(docs), dict(Counter(d["tipo"] + " " + d["campo"].split("[")[0] for d in docs)))
        return 0
    import boto3
    cliente = boto3.Session(profile_name=a.perfil, region_name=REGION).client("accessanalyzer")
    for docs in por_perfil.values():
        for d in docs:
            d["hallazgos"] = validar(cliente, d)
            time.sleep(0.1)
    r = informe(por_perfil)
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: r[k] for k in ("por_perfil", "hallazgos_por_tipo", "veredicto")}, ensure_ascii=False))
    return 0 if r["veredicto"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
