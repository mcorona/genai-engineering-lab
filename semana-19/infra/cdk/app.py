"""Week 19, activity 3: foundation stack (CDK, Python). Synthesis only; $0, no AWS calls.

Two stacks per profile (PERFIL=lab|prod, default lab; the profile values are in ../../spike/perfiles.json):

- semana19-control (persistent, $0/h). Permission boundary, freeze policy (attached by the budget action), the
  execution policy for the CDK bootstrap, the deploy role, the budget with its action, and Cost Anomaly Detection.
  It has no assets, so it is deployed with `aws cloudformation deploy` before the bootstrap exists.
- semana19-base (ephemeral). KMS key, VPC (private isolated subnets, no internet gateway, no NAT), S3 gateway
  endpoint, interface endpoints of ADR 0005 in one AZ in lab (ADR 0006), security groups and VPC flow logs.

Every role created by these stacks gets the permission boundary semana19-limite (Aspect). Every log group gets a
retention (Aspect). cdk-nag AwsSolutions runs last; each suppression carries its reason.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import aws_cdk as cdk
import jsii
from aws_cdk import Aspects, Aws, CfnParameter, Duration, IAspect, RemovalPolicy, Stack, Tags
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_rds as rds
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3vectors as s3v
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from cdk_nag import AwsSolutionsChecks, NagPackSuppression, NagSuppressions
from constructs import Construct

from excepciones import EXCEPCIONES

PERFILES = json.loads((Path(__file__).resolve().parents[2] / "spike" / "perfiles.json").read_text(encoding="utf-8"))
PERFIL = os.environ.get("PERFIL", "lab")
CFG = PERFILES[PERFIL]
BORRADO = RemovalPolicy.RETAIN if CFG["politica_borrado"] == "RETAIN" else RemovalPolicy.DESTROY
REGION = "us-east-1"

# Names fixed in the repo. They are not secrets and they contain no account ID.
LIMITE = "semana19-limite"
CONGELAR = "semana19-congelar"
EJECUCION_CFN = "semana19-cfn-exec"
EJECUCION_CFN_DATOS = "semana19-cfn-exec-datos"
DESPLIEGUE = "semana19-despliegue"
OPERADOR_ROL = "semana19-operador"
OPERADOR_LIMITE = "semana19-operador-limite"
ACCIONES_LECTURA_OPERADOR = [
    "cloudformation:DescribeStacks", "cloudformation:ListStacks", "cloudformation:DescribeStackEvents",
    "ec2:DescribeVpcs", "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups", "ec2:DescribeVpcEndpoints",
    "ec2:DescribeFlowLogs", "ec2:DescribeRouteTables", "ec2:DescribeInternetGateways",
    "ec2:DescribeNatGateways", "kms:ListAliases", "kms:ListKeys", "kms:DescribeKey",
    "kms:GetKeyRotationStatus", "logs:DescribeLogGroups", "iam:GetRole", "iam:ListRoles",
    "budgets:ViewBudget", "budgets:DescribeBudgetActionsForAccount", "lambda:GetFunction",
    "lambda:ListFunctions", "rds:DescribeDBInstances", "s3:ListAllMyBuckets"]
ROL_PRESUPUESTO = "semana19-accion-presupuesto"
OPERADOR = "manuel-admin"
PRESUPUESTO = "semana19"
PRESUPUESTO_USD = 5.0
PREFIJO_ROLES_CDK = "cdk-s19-"
ETIQUETA_COSTO = "user:proyecto$semana19"
GRUPO_FLOW_LOGS = "/semana19/base/flowlogs"
PREFIJO_LOGS = "/semana19/"

ARN_PARTICION = f"arn:{Aws.PARTITION}"
ARN_OPERADOR_LIMITE = f"arn:{Aws.PARTITION}:iam::{Aws.ACCOUNT_ID}:policy/{OPERADOR_LIMITE}"




def arn_iam(recurso: str) -> str:
    return f"{ARN_PARTICION}:iam::{Aws.ACCOUNT_ID}:{recurso}"


ARN_LIMITE = arn_iam(f"policy/{LIMITE}")
ARN_CONGELAR = arn_iam(f"policy/{CONGELAR}")
ARN_EJECUCION_CFN = arn_iam(f"policy/{EJECUCION_CFN}")
ARN_EJECUCION_CFN_DATOS = arn_iam(f"policy/{EJECUCION_CFN_DATOS}")
ARN_DESPLIEGUE = arn_iam(f"role/{DESPLIEGUE}")

# Create and update actions that the freeze denies on the deploy role, the CDK deploy role and the CDK execution
# role. Delete actions are not here: destroying must keep working while the budget action is on.
CREAR_Y_ACTUALIZAR = [
    "cloudformation:CreateStack", "cloudformation:UpdateStack", "cloudformation:CreateChangeSet",
    "cloudformation:ExecuteChangeSet",
    "ec2:Create*", "ec2:Modify*", "ec2:Associate*", "ec2:Attach*", "ec2:Authorize*",
    "iam:Create*", "iam:Put*", "iam:Attach*", "iam:Update*",
    "kms:Create*", "kms:Put*", "kms:Enable*", "kms:TagResource",
    "logs:Create*", "logs:Put*",
    "s3:CreateBucket", "s3:PutObject", "s3:PutBucket*",
    "lambda:Create*", "lambda:Update*",
    "states:Create*", "states:Update*",
    "ecr:Create*", "ecr:Put*",
    "ssm:PutParameter",
    "budgets:Create*", "budgets:Update*", "ce:Create*", "ce:Update*",
    "rds:Create*", "rds:Modify*",
    "bedrock:Create*", "bedrock:Update*",
    "bedrock-agentcore:Create*", "bedrock-agentcore:Update*",
]


def _declaracion(**kwargs) -> iam.PolicyStatement:
    return iam.PolicyStatement(**kwargs)


def politica_limite() -> list[iam.PolicyStatement]:
    """Maximum permissions of any role the stacks create. Roles get only what they need inside this."""
    return [
        _declaracion(sid="LogsDelGrupoDelProyecto", actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                     resources=[f"arn:{Aws.PARTITION}:logs:{REGION}:{Aws.ACCOUNT_ID}:log-group:{PREFIJO_LOGS}*"]),
        _declaracion(sid="LogsDescribir", actions=["logs:DescribeLogGroups", "logs:DescribeLogStreams"],
                     resources=["*"]),
        _declaracion(sid="CdkAssumeRoles", actions=["sts:AssumeRole"],
                     resources=[arn_iam(f"role/{PREFIJO_ROLES_CDK}*")]),
        _declaracion(sid="CloudFormationLeer", actions=["cloudformation:Describe*", "cloudformation:Get*",
                                                        "cloudformation:List*"], resources=["*"]),
        _declaracion(sid="AdjuntarPoliticasAlRolDeDespliegue", actions=["iam:AttachRolePolicy", "iam:DetachRolePolicy"],
                     resources=[ARN_DESPLIEGUE]),
        _declaracion(sid="RestringirSgPorDefecto", actions=["ec2:DescribeSecurityGroups",
                                                            "ec2:RevokeSecurityGroupIngress",
                                                            "ec2:RevokeSecurityGroupEgress"], resources=["*"]),
    ]


def politica_congelar() -> list[iam.PolicyStatement]:
    return [_declaracion(sid="NoCrearNiActualizarMientrasEsteActiva", effect=iam.Effect.DENY,
                         actions=CREAR_Y_ACTUALIZAR, resources=["*"])]


def politica_ejecucion_cfn() -> list[iam.PolicyStatement]:
    """Execution policy of the CDK bootstrap (not AdministratorAccess). Roles only with the boundary attached."""
    grupos = f"arn:{Aws.PARTITION}:logs:{REGION}:{Aws.ACCOUNT_ID}:log-group:{PREFIJO_LOGS}*"
    return [
        _declaracion(sid="VpcYRedes", actions=[
            "ec2:CreateVpc", "ec2:DeleteVpc", "ec2:ModifyVpcAttribute", "ec2:CreateSubnet", "ec2:DeleteSubnet",
            "ec2:CreateRouteTable", "ec2:DeleteRouteTable", "ec2:AssociateRouteTable", "ec2:DisassociateRouteTable",
            "ec2:CreateSecurityGroup", "ec2:DeleteSecurityGroup", "ec2:AuthorizeSecurityGroupIngress",
            "ec2:AuthorizeSecurityGroupEgress", "ec2:RevokeSecurityGroupIngress", "ec2:RevokeSecurityGroupEgress",
            "ec2:CreateVpcEndpoint", "ec2:DeleteVpcEndpoints", "ec2:ModifyVpcEndpoint",
            "ec2:CreateFlowLogs", "ec2:DeleteFlowLogs", "ec2:CreateTags", "ec2:DeleteTags", "ec2:Describe*",
            "ec2:CreateInternetGateway", "ec2:DeleteInternetGateway"], resources=["*"]),
        _declaracion(sid="LlavesKms", actions=[
            "kms:CreateKey", "kms:CreateAlias", "kms:DeleteAlias", "kms:EnableKeyRotation", "kms:PutKeyPolicy",
            "kms:ScheduleKeyDeletion", "kms:TagResource", "kms:DescribeKey", "kms:GetKeyPolicy",
            "kms:GetKeyRotationStatus", "kms:ListResourceTags", "kms:CancelKeyDeletion"], resources=["*"]),
        _declaracion(sid="GruposDeLogs", actions=[
            "logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:PutRetentionPolicy", "logs:DeleteRetentionPolicy",
            "logs:AssociateKmsKey", "logs:DisassociateKmsKey", "logs:TagResource", "logs:UntagResource",
            "logs:TagLogGroup"], resources=[grupos]),
        _declaracion(sid="DescribirGruposDeLogs", actions=["logs:DescribeLogGroups"], resources=["*"]),
        _declaracion(sid="LeerRolFlowLogs", actions=["iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies",
                                                     "iam:ListAttachedRolePolicies", "iam:ListRoleTags"],
                     resources=[arn_iam("role/semana19-flow-logs")]),
        _declaracion(sid="BorrarRolFlowLogs", actions=["iam:DeleteRole", "iam:DeleteRolePolicy", "iam:DetachRolePolicy"],
                     resources=[arn_iam("role/semana19-flow-logs")]),
        _declaracion(sid="PasarRolFlowLogsASuServicio", actions=["iam:PassRole"],
                     resources=[arn_iam("role/semana19-flow-logs")],
                     conditions={"StringEquals": {"iam:PassedToService": "vpc-flow-logs.amazonaws.com"}}),
        _declaracion(sid="PasarRolDelCustomResourceDelProyecto", actions=["iam:PassRole"],
                     resources=[arn_iam("role/semana19-base-CustomVpcRestrictDefaultSGCustomResou*")],
                     conditions={"StringEquals": {"iam:PassedToService": "lambda.amazonaws.com"}}),
        _declaracion(sid="PoliticasYAdjuntosDeRolesDelBase", actions=[
            "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy", "iam:ListRolePolicies",
            "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:ListAttachedRolePolicies", "iam:ListRoleTags"],
            resources=[arn_iam("role/semana19-base-*")]),
        _declaracion(sid="BorrarRolesDelBase", actions=["iam:DeleteRole"],
                     resources=[arn_iam("role/semana19-base-*")]),
        _declaracion(sid="LeerActivosDelBootstrap", actions=["s3:GetObject", "s3:GetObjectVersion", "s3:GetBucketLocation",
                                                             "s3:ListBucket"],
                     resources=[f"arn:{Aws.PARTITION}:s3:::cdk-s19-assets-{Aws.ACCOUNT_ID}-{REGION}",
                                f"arn:{Aws.PARTITION}:s3:::cdk-s19-assets-{Aws.ACCOUNT_ID}-{REGION}/*"]),
        _declaracion(sid="DescifrarActivosConS3", actions=["kms:Decrypt", "kms:DescribeKey"], resources=["*"],
                     conditions={"StringEquals": {"kms:ViaService": f"s3.{REGION}.amazonaws.com"}}),
        _declaracion(sid="VersionDelBootstrap", actions=["ssm:GetParameter", "ssm:GetParameters"],
                     resources=[f"arn:{Aws.PARTITION}:ssm:{REGION}:{Aws.ACCOUNT_ID}:parameter/cdk-bootstrap/s19/version"]),
        _declaracion(sid="FuncionesDeCustomResourceDelProyecto", actions=[
            "lambda:CreateFunction", "lambda:DeleteFunction", "lambda:GetFunction", "lambda:UpdateFunctionCode",
            "lambda:UpdateFunctionConfiguration", "lambda:InvokeFunction", "lambda:AddPermission",
            "lambda:RemovePermission", "lambda:TagResource", "lambda:ListVersionsByFunction",
            "lambda:PublishVersion", "lambda:GetFunctionConfiguration"],
            resources=[f"arn:{Aws.PARTITION}:lambda:{REGION}:{Aws.ACCOUNT_ID}:function:semana19-*"]),
        _declaracion(sid="RolesConLimite", actions=[
            "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:PassRole", "iam:AttachRolePolicy",
            "iam:DetachRolePolicy", "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy",
            "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:TagRole", "iam:UntagRole",
            "iam:UpdateAssumeRolePolicy", "iam:ListRoleTags"],
            resources=[arn_iam(f"role/{PREFIJO_LOGS.strip('/')}*"), arn_iam("role/semana19-*")],
            conditions={"StringEquals": {"iam:PermissionsBoundary": ARN_LIMITE}}),
    ]


def politica_ejecucion_datos() -> list[iam.PolicyStatement]:
    """Second execution policy (6144-character limit per managed policy): what CloudFormation calls for stack datos."""
    return [
        # --- stack semana19-datos (activity 4): what CloudFormation calls while creating and deleting its resources.
        _declaracion(sid="SecretoDeLaBdPorCfn", actions=[
            "secretsmanager:CreateSecret", "secretsmanager:UpdateSecret", "secretsmanager:DeleteSecret",
            "secretsmanager:DescribeSecret", "secretsmanager:TagResource", "secretsmanager:UntagResource", "secretsmanager:GetResourcePolicy",
            "secretsmanager:PutResourcePolicy", "secretsmanager:DeleteResourcePolicy"], resources=["*"]),
        _declaracion(sid="ContrasenaGeneradaPorCfn", actions=["secretsmanager:GetRandomPassword"], resources=["*"]),
        _declaracion(sid="BaseDeDatosPostgresPorCfn", actions=[
            "rds:CreateDBInstance", "rds:DeleteDBInstance", "rds:ModifyDBInstance", "rds:AddTagsToResource",
            "rds:RemoveTagsFromResource", "rds:ListTagsForResource", "rds:CreateDBSubnetGroup",
            "rds:DeleteDBSubnetGroup", "rds:ModifyDBSubnetGroup"],
            resources=[f"arn:{Aws.PARTITION}:rds:{REGION}:{Aws.ACCOUNT_ID}:db:semana19-datos*",
                       f"arn:{Aws.PARTITION}:rds:{REGION}:{Aws.ACCOUNT_ID}:subgrp:semana19-datos*"]),
        _declaracion(sid="DescribirRdsPorCfn", actions=["rds:DescribeDBInstances", "rds:DescribeDBSubnetGroups"],
                     resources=["*"]),
        _declaracion(sid="LlaveParaRdsYSecretos", actions=[
            "kms:CreateGrant", "kms:ListGrants", "kms:DescribeKey"], resources=["*"],
            conditions={"StringEquals": {"kms:ViaService": [f"rds.{REGION}.amazonaws.com",
                                                             f"secretsmanager.{REGION}.amazonaws.com"]}}),
        _declaracion(sid="BucketDocsKbPorCfn", actions=[
            "s3:CreateBucket", "s3:DeleteBucket", "s3:PutEncryptionConfiguration",
            "s3:GetEncryptionConfiguration", "s3:PutBucketVersioning",
            "s3:GetBucketVersioning", "s3:PutBucketPublicAccessBlock", "s3:GetBucketPublicAccessBlock",
            "s3:PutBucketPolicy", "s3:GetBucketPolicy", "s3:DeleteBucketPolicy", "s3:PutBucketTagging",
            "s3:GetBucketTagging", "s3:GetBucketLocation", "s3:GetBucketAcl", "s3:PutBucketOwnershipControls",
            "s3:GetBucketOwnershipControls", "s3:ListBucket", "s3:ListBucketVersions", "s3:DeleteObject",
            "s3:DeleteObjectVersion"],
            resources=[f"arn:{Aws.PARTITION}:s3:::semana19-datos*"]),
        _declaracion(sid="VectoresKbPorCfn", actions=[
            "s3vectors:CreateVectorBucket", "s3vectors:GetVectorBucket", "s3vectors:DeleteVectorBucket",
            "s3vectors:CreateIndex", "s3vectors:GetIndex", "s3vectors:DeleteIndex", "s3vectors:ListIndexes",
            "s3vectors:TagResource", "s3vectors:UntagResource", "s3vectors:ListTagsForResource"],
            resources=[f"arn:{Aws.PARTITION}:s3vectors:{REGION}:{Aws.ACCOUNT_ID}:bucket/semana19-kb-*",
                       f"arn:{Aws.PARTITION}:s3vectors:{REGION}:{Aws.ACCOUNT_ID}:bucket/semana19-kb-*/index/*"]),
        # CreateKnowledgeBase is authorized against '*': the knowledge base has no ARN before it exists.
        _declaracion(sid="CrearKnowledgeBasePorCfn", actions=["bedrock:CreateKnowledgeBase"], resources=["*"]),
        _declaracion(sid="KnowledgeBasePorCfn", actions=[
            "bedrock:GetKnowledgeBase", "bedrock:UpdateKnowledgeBase",
            "bedrock:DeleteKnowledgeBase", "bedrock:CreateDataSource", "bedrock:GetDataSource",
            "bedrock:UpdateDataSource", "bedrock:DeleteDataSource", "bedrock:ListDataSources",
            "bedrock:TagResource", "bedrock:UntagResource", "bedrock:ListTagsForResource"],
            resources=[f"arn:{Aws.PARTITION}:bedrock:{REGION}:{Aws.ACCOUNT_ID}:knowledge-base/*"]),
        _declaracion(sid="RolesDelDatosPorCfn", actions=[
            "iam:GetRole", "iam:DeleteRole", "iam:GetRolePolicy", "iam:PutRolePolicy", "iam:DeleteRolePolicy",
            "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:ListRolePolicies",
            "iam:ListAttachedRolePolicies", "iam:ListRoleTags", "iam:TagRole", "iam:UntagRole"],
            resources=[arn_iam("role/semana19-kb"), arn_iam("role/semana19-datos-*")]),
        _declaracion(sid="PasarRolesDelDatosAKbYLambda", actions=["iam:PassRole"],
                     resources=[arn_iam("role/semana19-kb"), arn_iam("role/semana19-datos-*")],
                     conditions={"StringEquals": {"iam:PassedToService": [
                         "bedrock.amazonaws.com", "lambda.amazonaws.com"]}}),
        _declaracion(sid="ConcurrenciaDelCargador", actions=[
            "lambda:PutFunctionConcurrency", "lambda:DeleteFunctionConcurrency",
            "lambda:GetFunctionConcurrency"],
            resources=[f"arn:{Aws.PARTITION}:lambda:{REGION}:{Aws.ACCOUNT_ID}:function:semana19-*"]),
    ]


def suprimir_iam5(constructo, sids: list[str]) -> None:
    """cdk-nag suppression for IAM5 under this construct; the reason is the register entry for each Sid."""
    razon = " | ".join(f"{s}: {EXCEPCIONES[s]}" for s in sids)
    NagSuppressions.add_resource_suppressions(
        constructo, [NagPackSuppression(id="AwsSolutions-IAM5", reason=razon)], apply_to_children=True)


def saltar_checkov(constructo, omisiones: dict[str, str]) -> None:
    """checkov skip with a reason, merged with any cdk-nag metadata already on the resource."""
    recurso = constructo.node.default_child if hasattr(constructo.node, "default_child") and constructo.node.default_child else constructo
    md = dict(recurso.cfn_options.metadata or {})
    checkov = dict(md.get("checkov", {}))
    lista = list(checkov.get("skip", []))
    for regla, comentario in omisiones.items():
        lista.append({"id": regla, "comment": comentario})
    checkov["skip"] = lista
    md["checkov"] = checkov
    recurso.cfn_options.metadata = md


@jsii.implements(IAspect)
class AplicarLimite:
    """Every CfnRole in the stack gets the permission boundary (also the roles CDK generates for custom resources)."""

    def visit(self, node):
        # CDK's own custom resource roles are generic CfnResource nodes, so match by type, not by class.
        if getattr(node, "cfn_resource_type", None) == "AWS::IAM::Role":
            # The operator role has its own boundary: read-only, so it cannot be wider than its purpose.
            if node.node.path.endswith("/Operador/Resource"):
                node.add_property_override("PermissionsBoundary", ARN_OPERADOR_LIMITE)
            else:
                node.add_property_override("PermissionsBoundary", ARN_LIMITE)


@jsii.implements(IAspect)
class RetencionDeLogs:
    """A log group without retention gets the profile's default. The test fails if any stays without one."""

    def visit(self, node):
        if isinstance(node, logs.CfnLogGroup) and node.retention_in_days is None:
            node.retention_in_days = CFG["retencion_logs_dias"]


class Control(Stack):
    """No assets and no BootstrapVersion parameter: it is deployed before the bootstrap exists."""

    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, synthesizer=cdk.LegacyStackSynthesizer(), **kwargs)
        correo = CfnParameter(self, "CorreoAlerta", type="String", default="",
                              description="Correo de alertas (se pasa al desplegar con ALERTA_EMAIL; no va en el repo).")
        bootstrap = CfnParameter(self, "BootstrapCreado", type="String", default="false",
                                 allowed_values=["true", "false"],
                                 description="true cuando el bootstrap s19 ya existe: la acción congela también los roles cdk-s19-*.")
        hay_bootstrap = cdk.CfnCondition(self, "HayBootstrap", expression=cdk.Fn.condition_equals(
            bootstrap.value_as_string, "true"))
        roles_congelados = cdk.Token.as_list(cdk.Fn.condition_if(
            hay_bootstrap.logical_id,
            [DESPLIEGUE, f"cdk-s19-deploy-role-{Aws.ACCOUNT_ID}-{REGION}", f"cdk-s19-cfn-exec-role-{Aws.ACCOUNT_ID}-{REGION}"],
            [DESPLIEGUE]))

        limite = iam.ManagedPolicy(self, "Limite", managed_policy_name=LIMITE, statements=politica_limite(),
                                   description="Permission boundary of every role created by the week 19 stacks.")
        congelar = iam.ManagedPolicy(self, "Congelar", managed_policy_name=CONGELAR,
                                     statements=politica_congelar(),
                                     description="Attached by the budget action at 100%. Denies create and update only.")
        ejecucion = iam.ManagedPolicy(self, "EjecucionCfn", managed_policy_name=EJECUCION_CFN,
                                      statements=politica_ejecucion_cfn(),
                                      description="CloudFormation execution policies of the CDK bootstrap (not AdministratorAccess).")
        ejecucion_datos = iam.ManagedPolicy(self, "EjecucionCfnDatos", managed_policy_name=EJECUCION_CFN_DATOS,
                                            statements=politica_ejecucion_datos(),
                                            description="Second CloudFormation execution policy: stack semana19-datos (activity 4).")

        despliegue = iam.Role(
            self, "Despliegue", role_name=DESPLIEGUE,
            assumed_by=iam.ArnPrincipal(arn_iam(f"user/{OPERADOR}")),
            max_session_duration=Duration.hours(1),
            description="Deploy role: the only one that can assume the CDK roles; creates roles only with the boundary.")
        despliegue.add_to_principal_policy(_declaracion(sid="AsumirRolesCdk", actions=["sts:AssumeRole"],
                                                        resources=[arn_iam(f"role/{PREFIJO_ROLES_CDK}*")]))
        despliegue.add_to_principal_policy(_declaracion(sid="LeerCloudFormation", actions=[
            "cloudformation:Describe*", "cloudformation:Get*", "cloudformation:List*"], resources=["*"]))
        despliegue.add_to_principal_policy(_declaracion(sid="CrearRolesSoloConLimite", actions=["iam:CreateRole"],
                                                        resources=[arn_iam("role/semana19-*")],
                                                        conditions={"StringEquals": {"iam:PermissionsBoundary": ARN_LIMITE}}))
        despliegue.add_to_principal_policy(_declaracion(
            sid="NoQuitarNiCambiarElLimite", effect=iam.Effect.DENY, actions=[
                "iam:DeleteRolePermissionsBoundary", "iam:PutRolePermissionsBoundary"],
            resources=[arn_iam("role/semana19-*")]))
        despliegue.add_to_principal_policy(_declaracion(
            sid="NoModificarLaPoliticaDelLimiteNiDeLaCongelacion", effect=iam.Effect.DENY, actions=[
                "iam:CreatePolicyVersion", "iam:DeletePolicy", "iam:DeletePolicyVersion",
                "iam:SetDefaultPolicyVersion"],
            resources=[ARN_LIMITE, ARN_CONGELAR, ARN_EJECUCION_CFN, ARN_EJECUCION_CFN_DATOS]))
        despliegue.add_to_principal_policy(_declaracion(
            sid="NoModificarseASiMismo", effect=iam.Effect.DENY, actions=[
                "iam:UpdateAssumeRolePolicy", "iam:PutRolePolicy", "iam:AttachRolePolicy", "iam:DetachRolePolicy",
                "iam:DeleteRole", "iam:PutRolePermissionsBoundary", "iam:DeleteRolePermissionsBoundary"],
            resources=[ARN_DESPLIEGUE]))

        rol_presupuesto = iam.Role(
            self, "RolPresupuesto", role_name=ROL_PRESUPUESTO,
            assumed_by=iam.ServicePrincipal("budgets.amazonaws.com",
                                            conditions={"StringEquals": {"aws:SourceAccount": Aws.ACCOUNT_ID}}),
            description="Execution role of the budget action: attaches the freeze policy to the deploy role only.")
        rol_presupuesto.add_to_principal_policy(_declaracion(
            sid="CongelarSoloElRolDeDespliegue", actions=["iam:AttachRolePolicy", "iam:DetachRolePolicy"],
            resources=[ARN_DESPLIEGUE]))

        destinatario = [budgets.CfnBudget.SubscriberProperty(address=correo.value_as_string, subscription_type="EMAIL")]

        presupuesto = budgets.CfnBudget(
            self, "Presupuesto",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name=PRESUPUESTO,
                budget_limit=budgets.CfnBudget.SpendProperty(amount=PRESUPUESTO_USD, unit="USD"),
                time_unit="MONTHLY", budget_type="COST",
                cost_filters={"TagKeyValue": [ETIQUETA_COSTO]},
                cost_types=budgets.CfnBudget.CostTypesProperty(
                    include_tax=True, include_subscription=True, use_blended=False, include_refund=False,
                    include_credit=False, include_upfront=True, include_recurring=True,
                    include_other_subscription=True, include_support=True, include_discount=True,
                    use_amortized=False)),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        comparison_operator="GREATER_THAN", notification_type=tipo, threshold=umbral,
                        threshold_type="PERCENTAGE"),
                    subscribers=destinatario)
                for tipo, umbral in [("ACTUAL", 50), ("ACTUAL", 100), ("FORECASTED", 100)]])

        budgets.CfnBudgetsAction(
            self, "AccionPresupuesto", budget_name=PRESUPUESTO, notification_type="ACTUAL",
            action_type="APPLY_IAM_POLICY",
            action_threshold=budgets.CfnBudgetsAction.ActionThresholdProperty(type="PERCENTAGE", value=100),
            definition=budgets.CfnBudgetsAction.DefinitionProperty(
                iam_action_definition=budgets.CfnBudgetsAction.IamActionDefinitionProperty(
                    policy_arn=congelar.managed_policy_arn, roles=roles_congelados)),
            execution_role_arn=rol_presupuesto.role_arn, approval_model="AUTOMATIC",
            subscribers=[budgets.CfnBudgetsAction.SubscriberProperty(address=correo.value_as_string,
                                                                     type="EMAIL")])
        presupuesto.add_dependency(rol_presupuesto.node.default_child)

        suprimir_iam5(limite, ["LogsDelGrupoDelProyecto", "LogsDescribir", "CdkAssumeRoles", "CloudFormationLeer",
                               "RestringirSgPorDefecto"])
        saltar_checkov(limite, {"CKV_AWS_111": "Lectura y revocación de SG por defecto sin ARN, y nombres por prefijo semana19-*/cdk-s19-*; ver EXCEPCIONES."})
        suprimir_iam5(congelar, ["NoCrearNiActualizarMientrasEsteActiva"])
        suprimir_iam5(ejecucion, ["VpcYRedes", "LlavesKms", "GruposDeLogs", "DescribirGruposDeLogs",
                                  "FuncionesDeCustomResourceDelProyecto", "RolesConLimite"])
        saltar_checkov(ejecucion_datos, {
            "CKV_AWS_111": "Creación de recursos del stack datos sin ARN previo (secreto, base, buckets, Knowledge Base); ver EXCEPCIONES.",
            "CKV_AWS_109": "Roles semana19-kb y semana19-datos-* sin condición de límite en las acciones de gestión: los roles se crean con semana19-limite (aplicado por el Aspect), y iam:PassRole solo hacia bedrock y lambda."})
        suprimir_iam5(ejecucion_datos, ["SecretoDeLaBdPorCfn", "ContrasenaGeneradaPorCfn", "DescribirRdsPorCfn",
                                        "LlaveParaRdsYSecretos", "BaseDeDatosPostgresPorCfn", "BucketDocsKbPorCfn",
                                        "VectoresKbPorCfn", "KnowledgeBasePorCfn", "CrearKnowledgeBasePorCfn",
                                        "RolesDelDatosPorCfn", "PasarRolesDelDatosAKbYLambda", "ConcurrenciaDelCargador"])
        saltar_checkov(ejecucion, {
            "CKV_AWS_111": "Creación de recursos del proyecto sin ARN previo (VPC, llaves, grupos); ver EXCEPCIONES.",
            "CKV_AWS_109": "Gestión de roles limitada a nombres semana19-* y obligatoriamente con el límite (condición iam:PermissionsBoundary); ver EXCEPCIONES."})
        suprimir_iam5(despliegue, ["AsumirRolesCdk", "LeerCloudFormation", "CrearRolesSoloConLimite",
                                   "NoQuitarNiCambiarElLimite"])
        operador_limite = iam.ManagedPolicy(
            self, "OperadorLimite", managed_policy_name=OPERADOR_LIMITE,
            statements=[_declaracion(sid="LeerInventario", actions=ACCIONES_LECTURA_OPERADOR, resources=["*"])],
            description="Permission boundary of the operator role: read-only inventory, nothing else.")
        operador = iam.Role(
            self, "Operador", role_name=OPERADOR_ROL,
            assumed_by=iam.ArnPrincipal(arn_iam(f"user/{OPERADOR}")),
            max_session_duration=Duration.hours(1),
            description="Operator role: read-only inventory of the lab. It cannot create, change or delete resources.")
        operador.add_to_principal_policy(_declaracion(sid="LeerInventario", actions=ACCIONES_LECTURA_OPERADOR,
                                                      resources=["*"]))
        suprimir_iam5(operador_limite, ["LeerInventario"])
        suprimir_iam5(operador, ["LeerInventario"])
        cdk.CfnOutput(self, "ArnOperador", value=operador.role_arn)
        cdk.CfnOutput(self, "ArnLimite", value=limite.managed_policy_arn)
        cdk.CfnOutput(self, "ArnDespliegue", value=despliegue.role_arn)
        cdk.CfnOutput(self, "ArnCongelar", value=congelar.managed_policy_arn)
        cdk.CfnOutput(self, "ArnEjecucionCfn", value=ejecucion.managed_policy_arn)
        cdk.CfnOutput(self, "ArnEjecucionCfnDatos", value=ejecucion_datos.managed_policy_arn)


class Base(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)
        region = self.region
        cuenta = self.account

        llave = kms.Key(
            self, "Llave", alias="alias/semana19", enable_key_rotation=True,
            removal_policy=BORRADO, pending_window=Duration.days(CFG["ventana_borrado_llave_dias"]),
            description="Week 19 customer managed key: logs and the stack's data.",
            policy=iam.PolicyDocument(statements=[
                _declaracion(sid="RaizDeLaCuenta", actions=["kms:*"],
                             principals=[iam.ArnPrincipal(f"arn:{Aws.PARTITION}:iam::{cuenta}:root")],
                             resources=["*"]),
                _declaracion(sid="RolesConNombre", actions=[
                    "kms:Encrypt", "kms:Decrypt", "kms:ReEncryptFrom", "kms:ReEncryptTo", "kms:GenerateDataKey",
                    "kms:GenerateDataKeyWithoutPlaintext", "kms:DescribeKey", "kms:CreateGrant", "kms:ListGrants"],
                    principals=[iam.ArnPrincipal(f"arn:{Aws.PARTITION}:iam::{cuenta}:role/{DESPLIEGUE}"),
                                iam.ArnPrincipal(f"arn:{Aws.PARTITION}:iam::{cuenta}:role/cdk-s19-cfn-exec-role-{cuenta}-{region}")],
                    resources=["*"]),
                _declaracion(sid="LogsDelProyectoConLaLlave", actions=[
                    "kms:Encrypt", "kms:Decrypt", "kms:ReEncryptFrom", "kms:ReEncryptTo", "kms:GenerateDataKey",
                    "kms:GenerateDataKeyWithoutPlaintext", "kms:DescribeKey"],
                    principals=[iam.ServicePrincipal(f"logs.{region}.amazonaws.com")],
                    resources=["*"],
                    conditions={"ArnLike": {"kms:EncryptionContext:aws:logs:arn":
                                            f"arn:{Aws.PARTITION}:logs:{region}:{cuenta}:log-group:{PREFIJO_LOGS}*"}}),
            ]))

        grupo = logs.CfnLogGroup(
            self, "GrupoFlowLogs", log_group_name=GRUPO_FLOW_LOGS,
            retention_in_days=CFG["retencion_flow_logs_dias"], kms_key_id=llave.key_arn)
        grupo.apply_removal_policy(BORRADO)

        rol_flow = iam.Role(
            self, "RolFlowLogs", role_name="semana19-flow-logs",
            assumed_by=iam.ServicePrincipal("vpc-flow-logs.amazonaws.com",
                                            conditions={"StringEquals": {"aws:SourceAccount": cuenta}}),
            description="Writes the VPC flow logs to their log group only.")
        rol_flow.add_to_principal_policy(_declaracion(
            sid="EscribirSoloEnSuGrupo", actions=["logs:CreateLogStream", "logs:PutLogEvents"],
            resources=[f"arn:{Aws.PARTITION}:logs:{region}:{cuenta}:log-group:{GRUPO_FLOW_LOGS}:*"]))
        rol_flow.add_to_principal_policy(_declaracion(
            sid="DescribirGruposParaFlowLogs", actions=["logs:DescribeLogGroups", "logs:DescribeLogStreams"],
            resources=["*"]))

        red = ec2.Vpc(
            self, "Red", ip_addresses=ec2.IpAddresses.cidr("10.19.0.0/16"),
            availability_zones=[f"{REGION}{letra}" for letra in "abc"[:max(2, CFG["azs"])]],
            nat_gateways=0,
            restrict_default_security_group=True,
            subnet_configuration=[ec2.SubnetConfiguration(
                name="privada", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24)])
        red.add_flow_log("FlujosDeLaRed", destination=ec2.FlowLogDestination.to_cloud_watch_logs(
            logs.LogGroup.from_log_group_arn(self, "GrupoFlowLogsRef", grupo.attr_arn), rol_flow),
            traffic_type=ec2.FlowLogTrafficType.ALL)

        self.red = red
        self.llave = llave
        subredes_privadas = red.isolated_subnets
        tablas = [s.route_table.route_table_id for s in subredes_privadas]
        ids_subredes = [s.subnet_id for s in subredes_privadas]
        ids_una_az = ids_subredes[:CFG["azs"]]  # ADR 0006: 1 AZ in lab, 3 in prod

        sg_herramientas = ec2.SecurityGroup(
            self, "SgHerramientas", vpc=red, allow_all_outbound=False,
            description="Tools Lambda (activity 6). Empty in activity 3: no rules.")

        sg_endpoints = ec2.SecurityGroup(
            self, "SgEndpoints", vpc=red, allow_all_outbound=False,
            description="Interface endpoints: HTTPS only from the tools Lambda security group.")
        sg_endpoints.add_ingress_rule(sg_herramientas, ec2.Port.tcp(443), "HTTPS desde la Lambda de herramientas")

        politica_cuenta = {"Version": "2012-10-17", "Statement": [{
            "Sid": "SoloLaCuenta", "Effect": "Allow", "Principal": "*", "Action": "*", "Resource": "*",
            "Condition": {"StringEquals": {"aws:PrincipalAccount": cuenta}}}]}

        ec2.CfnVPCEndpoint(
            self, "EndpointS3", vpc_id=red.vpc_id, service_name=f"com.amazonaws.{region}.s3",
            vpc_endpoint_type="Gateway", route_table_ids=tablas, policy_document=politica_cuenta)

        for nombre, servicio in [("Logs", "logs"), ("StepFunctions", "states")]:
            ec2.CfnVPCEndpoint(
                self, f"Endpoint{nombre}", vpc_id=red.vpc_id, service_name=f"com.amazonaws.{region}.{servicio}",
                vpc_endpoint_type="Interface", subnet_ids=ids_una_az,
                security_group_ids=[sg_endpoints.security_group_id], private_dns_enabled=True,
                policy_document=politica_cuenta)

        suprimir_iam5(rol_flow, ["EscribirSoloEnSuGrupo", "DescribirGruposParaFlowLogs", "-"])
        Tags.of(self).add("proyecto", "semana19")
        Tags.of(self).add("perfil", PERFIL)


class Datos(Stack):
    """Activity 4, first slice: the lab's PostgreSQL in the base VPC. Single AZ, encrypted with the stack key,
    no public access, IAM authentication. The loader, the Knowledge Base and the agent role come in later slices."""

    def __init__(self, scope: Construct, id: str, red: ec2.Vpc, llave: kms.IKey, **kwargs):
        super().__init__(scope, id, **kwargs)

        sg_cargador = ec2.SecurityGroup(
            self, "SgCargador", vpc=red, allow_all_outbound=False,
            description="One-shot loader Lambda (activity 4): reaches PostgreSQL on 5432 only.")
        sg_bd = ec2.SecurityGroup(
            self, "SgBaseDeDatos", vpc=red, allow_all_outbound=False,
            description="PostgreSQL: 5432 only from the loader security group.")
        sg_bd.add_ingress_rule(sg_cargador, ec2.Port.tcp(5432), "PostgreSQL desde el cargador")
        sg_cargador.add_egress_rule(sg_bd, ec2.Port.tcp(5432), "PostgreSQL")

        bd = rds.DatabaseInstance(
            self, "PostgreSQL",
            engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.of("16.15", "16")),  # 16.15: bare "16" is deprecated for new instances
            instance_type=ec2.InstanceType("t4g.micro"),
            vpc=red,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            availability_zone=red.isolated_subnets[0].availability_zone,
            multi_az=False,
            publicly_accessible=False,
            allocated_storage=20,
            storage_type=rds.StorageType.GP3,
            storage_encrypted=True,
            storage_encryption_key=llave,
            iam_authentication=True,
            credentials=rds.Credentials.from_generated_secret("admin_legado", encryption_key=llave),
            backup_retention=Duration.days(1),
            delete_automated_backups=True,
            deletion_protection=False,
            auto_minor_version_upgrade=True,
            security_groups=[sg_bd],
            removal_policy=RemovalPolicy.DESTROY)

        self.bd = bd
        self.sg_cargador = sg_cargador
        NagSuppressions.add_resource_suppressions(bd, [NagPackSuppression(
            id="AwsSolutions-RDS11", reason="Puerto 5432 de PostgreSQL: el acceso lo limita el SG a la Lambda del cargador.")])
        NagSuppressions.add_resource_suppressions(bd, [NagPackSuppression(
            id="AwsSolutions-RDS10", reason="Protección contra borrado apagada solo en el laboratorio; el teardown debe borrarla. Documentado en el plan.")])
        NagSuppressions.add_resource_suppressions(bd, [NagPackSuppression(
            id="AwsSolutions-RDS3", reason="Single-AZ por diseño de laboratorio (plan, actividad 4).")])
        NagSuppressions.add_resource_suppressions_by_path(self, "/semana19-datos/PostgreSQL/Secret/Resource", [NagPackSuppression(
            id="AwsSolutions-SMG4", reason="Sin rotación automática en el laboratorio: la Lambda de rotación queda fuera de la actividad 4; la contraseña nunca sale del secreto cifrado con la llave del stack.")])
        # Secrets Manager endpoint: the loader reads the master password from inside the VPC (no internet).
        sg_endpoint_secretos = ec2.SecurityGroup(
            self, "SgEndpointSecretos", vpc=red, allow_all_outbound=False,
            description="Interface endpoint de Secrets Manager: HTTPS solo desde el cargador.")
        sg_endpoint_secretos.add_ingress_rule(sg_cargador, ec2.Port.tcp(443), "HTTPS desde el cargador")
        sg_cargador.add_egress_rule(sg_endpoint_secretos, ec2.Port.tcp(443), "HTTPS al endpoint de Secrets Manager")
        politica_cuenta = {"Version": "2012-10-17", "Statement": [{
            "Sid": "SoloLaCuenta", "Effect": "Allow", "Principal": "*", "Action": "*", "Resource": "*",
            "Condition": {"StringEquals": {"aws:PrincipalAccount": Aws.ACCOUNT_ID}}}]}
        ec2.CfnVPCEndpoint(
            self, "EndpointSecretos", vpc_id=red.vpc_id, service_name=f"com.amazonaws.{self.region}.secretsmanager",
            vpc_endpoint_type="Interface", subnet_ids=[red.isolated_subnets[0].subnet_id],
            security_group_ids=[sg_endpoint_secretos.security_group_id], private_dns_enabled=True,
            policy_document=politica_cuenta)

        # One-shot loader: seed 42, legado schema, copilot_ro and order_writer. Invoked by hand, once per session.
        cargador = lambda_.Function(
            self, "Cargador", runtime=lambda_.Runtime.PYTHON_3_13, handler="handler.handler",
            code=lambda_.Code.from_asset(str(Path(__file__).resolve().parents[1] / "loader")),
            timeout=Duration.seconds(300), memory_size=512,
            vpc=red, vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[sg_cargador], reserved_concurrent_executions=1,
            description="One-shot loader of the lab database (activity 4). Idempotent. Input: secret ARN and host.")
        saltar_checkov(cargador, {
            "CKV_AWS_116": "Cargador de un solo uso invocado a mano: el resultado vuelve en la respuesta de la invocación; no hay cola de reintentos que vigilar."})
        # Identity policy: grant_read would also grant decrypt on the key, which lives in the base stack.
        cargador.add_to_role_policy(_declaracion(sid="LeerElSecretoDeLaBd", actions=["secretsmanager:GetSecretValue"],
                                                 resources=[bd.secret.secret_arn]))
        # Identity policy, not llave.grant_decrypt: the key lives in the base stack and its policy already delegates to IAM.
        cargador.add_to_role_policy(_declaracion(sid="DescifrarConLaLlaveDelProyecto", actions=["kms:Decrypt", "kms:DescribeKey"],
                                                 resources=[llave.key_arn]))
        # bedrock-agent endpoint: the loader starts the KB ingestion job from inside the VPC.
        sg_endpoint_agente = ec2.SecurityGroup(
            self, "SgEndpointAgente", vpc=red, allow_all_outbound=False,
            description="Interface endpoint de Bedrock Agent: HTTPS solo desde el cargador.")
        sg_endpoint_agente.add_ingress_rule(sg_cargador, ec2.Port.tcp(443), "HTTPS desde el cargador")
        sg_cargador.add_egress_rule(sg_endpoint_agente, ec2.Port.tcp(443), "HTTPS al endpoint de Bedrock Agent")
        ec2.CfnVPCEndpoint(
            self, "EndpointBedrockAgent", vpc_id=red.vpc_id, service_name=f"com.amazonaws.{self.region}.bedrock-agent",
            vpc_endpoint_type="Interface", subnet_ids=[red.isolated_subnets[0].subnet_id],
            security_group_ids=[sg_endpoint_agente.security_group_id], private_dns_enabled=True,
            policy_document=politica_cuenta)

        # Knowledge Base: documents in an encrypted bucket, S3 Vectors as the store, Titan Text Embeddings V2.
        bucket_docs = s3.Bucket(
            self, "DocsKb", encryption=s3.BucketEncryption.KMS, encryption_key=llave, bucket_key_enabled=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True, versioned=True,
            removal_policy=RemovalPolicy.DESTROY, auto_delete_objects=False)
        vb = s3v.CfnVectorBucket(self, "VectoresKb", vector_bucket_name=f"semana19-kb-{Aws.ACCOUNT_ID}-{self.region}")
        indice = s3v.CfnIndex(
            self, "IndiceKb", vector_bucket_arn=vb.attr_vector_bucket_arn, index_name="legado-kb",
            data_type="float32", dimension=1024, distance_metric="cosine")
        indice.add_dependency(vb)
        modelo_titan = f"arn:{Aws.PARTITION}:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v2:0"
        rol_kb = iam.Role(
            self, "RolKb", role_name="semana19-kb",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com", conditions={
                "StringEquals": {"aws:SourceAccount": Aws.ACCOUNT_ID}}),
            description="Knowledge Base role: reads the docs bucket and the vector index, embeds with Titan V2.")
        rol_kb.add_to_principal_policy(_declaracion(sid="LeerLosDocs", actions=["s3:GetObject", "s3:ListBucket"],
                                                    resources=[bucket_docs.bucket_arn, bucket_docs.arn_for_objects("docs/*")]))
        rol_kb.add_to_principal_policy(_declaracion(sid="UsarElIndice", actions=[
            "s3vectors:GetIndex", "s3vectors:PutVectors", "s3vectors:GetVectors", "s3vectors:DeleteVectors",
            "s3vectors:QueryVectors", "s3vectors:ListVectors"], resources=[indice.attr_index_arn]))
        rol_kb.add_to_principal_policy(_declaracion(sid="EmbeberConTitan", actions=["bedrock:InvokeModel"],
                                                    resources=[modelo_titan]))
        rol_kb.add_to_principal_policy(_declaracion(sid="DescifrarDocs", actions=["kms:Decrypt", "kms:DescribeKey"],
                                                    resources=[llave.key_arn]))
        kb_lab = bedrock.CfnKnowledgeBase(
            self, "KbLegado", name="semana19-legado", role_arn=rol_kb.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=modelo_titan,
                    embedding_model_configuration=bedrock.CfnKnowledgeBase.EmbeddingModelConfigurationProperty(
                        bedrock_embedding_model_configuration=bedrock.CfnKnowledgeBase.BedrockEmbeddingModelConfigurationProperty(
                            dimensions=1024, embedding_data_type="FLOAT32")))),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="S3_VECTORS",
                s3_vectors_configuration=bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                    index_arn=indice.attr_index_arn)))
        kb_lab.node.add_dependency(rol_kb)
        fuente = bedrock.CfnDataSource(
            self, "FuenteDocsKb", knowledge_base_id=kb_lab.attr_knowledge_base_id, name="docs-legado",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3", s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=bucket_docs.bucket_arn, inclusion_prefixes=["docs/"])))
        fuente.add_dependency(kb_lab)
        cargador.add_to_role_policy(_declaracion(sid="EscribirDocsKb", actions=["s3:PutObject"],
                                                 resources=[bucket_docs.arn_for_objects("docs/*")]))
        cargador.add_to_role_policy(_declaracion(sid="IngestarKb", actions=["bedrock:StartIngestionJob"],
                                                 resources=[kb_lab.attr_knowledge_base_arn]))
        cargador.add_to_role_policy(_declaracion(sid="CifrarDocsKb", actions=["kms:GenerateDataKey", "kms:Encrypt"],
                                                 resources=[llave.key_arn]))
        NagSuppressions.add_resource_suppressions(bucket_docs, [NagPackSuppression(
            id="AwsSolutions-S1", reason="Registros de acceso al bucket de documentos apagados en el laboratorio: el contenido es sintético y los eventos quedan en CloudTrail.")])
        saltar_checkov(bucket_docs, {
            "CKV_AWS_18": "Registros de acceso apagados en el laboratorio (contenido sintético; eventos en CloudTrail), igual que AwsSolutions-S1."})
        suprimir_iam5(cargador, ["EscribirDocsKb"])
        suprimir_iam5(rol_kb, ["LeerLosDocs"])
        cdk.CfnOutput(self, "BucketDocsKb", value=bucket_docs.bucket_name)
        cdk.CfnOutput(self, "KbId", value=kb_lab.attr_knowledge_base_id)
        cdk.CfnOutput(self, "DataSourceId", value=fuente.attr_data_source_id)
        self.cargador = cargador
        cdk.CfnOutput(self, "ArnSecretoBd", value=bd.secret.secret_arn)
        cdk.CfnOutput(self, "HostBd", value=bd.db_instance_endpoint_address)
        cdk.CfnOutput(self, "NombreCargador", value=cargador.function_name)
        NagSuppressions.add_resource_suppressions(cargador.role, [NagPackSuppression(
            id="AwsSolutions-IAM4", reason="AWSLambdaVPCAccessExecutionRole: el cargador necesita crear interfaces de red en la VPC; la política administrada de AWS es la mínima para eso.")],
            apply_to_children=True)
        NagSuppressions.add_resource_suppressions(cargador, [NagPackSuppression(
            id="AwsSolutions-L1", reason="Runtime Python 3.13, el más reciente aprobado para el laboratorio; el cargador es de un solo uso.")])

        saltar_checkov(bd, {
            "CKV_AWS_157": "Single-AZ por diseño de laboratorio (plan, actividad 4); la alta disponibilidad es de producción.",
            "CKV_AWS_118": "Monitoreo mejorado apagado: agrega costo que el plan de costo no incluye; el laboratorio usa las métricas base."})
        Tags.of(self).add("proyecto", "semana19")
        Tags.of(self).add("perfil", PERFIL)


@jsii.implements(IAspect)
class OmitirCheckovEnProveedorCdk:
    """CDK creates the custom resource provider of restrictDefaultSecurityGroup during synthesis: it is outside the
    VPC by design, runs once and has no DLQ. The skip carries that reason."""

    def visit(self, node):
        if getattr(node, "cfn_resource_type", None) == "AWS::Lambda::Function" and "VpcRestrictDefaultSGCustomResourceProvider" in node.node.path:
            saltar_checkov(node, {
                "CKV_AWS_117": "Custom resource que CDK genera para vaciar el grupo de seguridad por defecto: corre una vez al crear la VPC; fuera de la VPC por diseño de CDK.",
                "CKV_AWS_116": "Custom resource de CDK: invocación única al crear la VPC; sin cola de mensajes muertos.",
                "CKV_AWS_115": "Custom resource de CDK: invocación única; sin límite de concurrencia.",
            })


def construir(app: cdk.App) -> None:
    control = Control(app, "semana19-control", env=cdk.Environment(region=REGION))
    base = Base(app, "semana19-base", env=cdk.Environment(region=REGION),
                synthesizer=cdk.DefaultStackSynthesizer(qualifier="s19"))
    datos = Datos(app, "semana19-datos", red=base.red, llave=base.llave, env=cdk.Environment(region=REGION),
                  synthesizer=cdk.DefaultStackSynthesizer(qualifier="s19"))
    for pila in (control, base, datos):
        Aspects.of(pila).add(AplicarLimite())
        Aspects.of(pila).add(RetencionDeLogs())
        Aspects.of(pila).add(OmitirCheckovEnProveedorCdk())
        Aspects.of(pila).add(AwsSolutionsChecks(verbose=True))


if __name__ == "__main__":
    app = cdk.App()
    construir(app)
    app.synth()
