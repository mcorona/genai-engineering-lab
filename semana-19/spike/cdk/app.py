"""Week 19, activity 2: minimal IaC spike (CDK, Python). Same stack as spike/terraform. Synth only, $0.

PERFIL=lab|prod (env) chooses the profile in ../perfiles.json. Default: lab.
"""
import json
import os
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from cdk_nag import AwsSolutionsChecks
from constructs import Construct


PERFILES = json.loads((Path(__file__).resolve().parents[1] / "perfiles.json").read_text(encoding="utf-8"))
PERFIL = os.environ.get("PERFIL", "lab")
CFG = PERFILES[PERFIL]
BORRADO = cdk.RemovalPolicy.RETAIN if CFG["politica_borrado"] == "RETAIN" else cdk.RemovalPolicy.DESTROY


class SpikeStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)
        llave = kms.Key(self, "Llave", enable_key_rotation=True, removal_policy=BORRADO,
                        pending_window=cdk.Duration.days(CFG["ventana_borrado_llave_dias"]))
        registros = s3.Bucket(
            self, "Registros", encryption=s3.BucketEncryption.KMS, encryption_key=llave,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True,
            removal_policy=BORRADO, auto_delete_objects=False, versioned=True)
        registros.node.default_child.cfn_options.metadata = {"checkov": {"skip": [{
            "id": "CKV_AWS_18",
            "comment": "Bucket de destino de los logs de acceso: AWS no permite que un bucket se registre a sí mismo."}]}}
        bucket = s3.Bucket(
            self, "Datos", encryption=s3.BucketEncryption.KMS, encryption_key=llave,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True,
            removal_policy=BORRADO, auto_delete_objects=False,
            versioned=True, server_access_logs_bucket=registros,
            server_access_logs_prefix="datos/")
        frontera = iam.ManagedPolicy(
            self, "Frontera", statements=[iam.PolicyStatement(
                actions=["s3:GetObject", "s3:PutObject"], resources=[bucket.arn_for_objects("*")])])
        frontera.node.default_child.cfn_options.metadata = {"cdk_nag": {"rules_to_suppress": [{
            "id": "AwsSolutions-IAM5",
            "reason": "La frontera limita al rol a los objetos de este bucket (arn_for_objects); el comodín es sobre objetos, no sobre el servicio."}]}}
        rol = iam.Role(
            self, "Rol", assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            permissions_boundary=frontera)
        rol.add_to_principal_policy(iam.PolicyStatement(actions=["s3:GetObject"], resources=[bucket.arn_for_objects("*")]))
        rol.node.find_child("DefaultPolicy").node.default_child.cfn_options.metadata = {"cdk_nag": {"rules_to_suppress": [{
            "id": "AwsSolutions-IAM5",
            "reason": "Solo s3:GetObject sobre los objetos de este bucket; el comodín es de recurso (objetos), no de acción."}]}}
        guardrail = bedrock.CfnGuardrail(
            self, "Guardrail", name="semana19-spike-guardrail",
            blocked_input_messaging="Bloqueado", blocked_outputs_messaging="Bloqueado",
            kms_key_arn=llave.key_arn,
            content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
                filters_config=[bedrock.CfnGuardrail.ContentFilterConfigProperty(
                    input_strength="HIGH", output_strength="HIGH", type="PROMPT_ATTACK")]))
        cdk.Tags.of(self).add("proyecto", "semana19")
        cdk.Tags.of(self).add("perfil", PERFIL)
        cdk.CfnOutput(self, "GuardrailId", value=guardrail.attr_guardrail_id)


app = cdk.App()
stack = SpikeStack(app, f"semana19-spike-{PERFIL}", env=cdk.Environment(account="000000000000", region="us-east-1"))
cdk.Aspects.of(stack).add(AwsSolutionsChecks(verbose=True))
app.synth()
