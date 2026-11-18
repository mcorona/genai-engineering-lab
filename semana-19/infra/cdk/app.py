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
from aws_cdk import aws_bedrockagentcore as agentcore
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_authorizers as apigwv2_auth
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_int
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
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
EJECUCION_CFN_IA = "semana19-cfn-exec-ia"  # split from semana19-cfn-exec: over the 6,144-character managed policy limit
EJECUCION_CFN_COMPUTO = "semana19-cfn-exec-computo"  # stack semana19-computo: approval workflow, Cognito and HTTP API
EJECUCION_CFN_DATOS = "semana19-cfn-exec-datos"
EJECUCION_CFN_AGENTES = "semana19-cfn-exec-agentes"  # activity 7: stacks semana19-gateway and semana19-agentes-comparacion
DESPLIEGUE = "semana19-despliegue"
ROL_PRESUPUESTO = "semana19-accion-presupuesto"
OPERADOR = "manuel-admin"
PRESUPUESTO = "semana19"
# Monthly (AWS Budgets has no weekly period). USD 10 since 2026-11-18, Manuel's weekly cap for week 19; it was 5.0.
PRESUPUESTO_USD = 10.0
PREFIJO_ROLES_CDK = "cdk-s19-"
ETIQUETA_COSTO = "user:proyecto$semana19"
GRUPO_FLOW_LOGS = "/semana19/base/flowlogs"
PREFIJO_LOGS = "/semana19/"

ARN_PARTICION = f"arn:{Aws.PARTITION}"




def arn_iam(recurso: str) -> str:
    return f"{ARN_PARTICION}:iam::{Aws.ACCOUNT_ID}:{recurso}"


ARN_LIMITE = arn_iam(f"policy/{LIMITE}")
ARN_CONGELAR = arn_iam(f"policy/{CONGELAR}")
ARN_EJECUCION_CFN = arn_iam(f"policy/{EJECUCION_CFN}")
ARN_EJECUCION_CFN_IA = arn_iam(f"policy/{EJECUCION_CFN_IA}")
ARN_EJECUCION_CFN_COMPUTO = arn_iam(f"policy/{EJECUCION_CFN_COMPUTO}")
ARN_EJECUCION_CFN_DATOS = arn_iam(f"policy/{EJECUCION_CFN_DATOS}")
ARN_EJECUCION_CFN_AGENTES = arn_iam(f"policy/{EJECUCION_CFN_AGENTES}")
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
    # Activity 7: the managed policy limit is 6,144 characters and this one was at 5,975. The statements with the same
    # actions (log writes) or with resource '*' and no condition are merged: the same permissions in fewer statements.
    return [
        # Log writes: the project's groups (/semana19/*, the guardrail creator's /semana19/ia/* among them) and the
        # loader's group, created by Lambda on its first run.
        _declaracion(sid="LogsDelLimite", actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                     resources=[f"arn:{Aws.PARTITION}:logs:{REGION}:{Aws.ACCOUNT_ID}:log-group:{PREFIJO_LOGS}*",
                                f"arn:{Aws.PARTITION}:logs:{REGION}:{Aws.ACCOUNT_ID}:log-group:/aws/lambda/semana19-datos*:*",
                                f"arn:{Aws.PARTITION}:logs:{REGION}:{Aws.ACCOUNT_ID}:log-group:{PREFIJO_LOGS}ia/*:*"]),
        # Actions AWS does not authorize on a narrower resource (one statement; the reasons per group are in EXCEPCIONES):
        # describing log groups; log delivery, which Step Functions validates with the machine's role (activity 6);
        # X-Ray traces; reading CloudFormation; the default security group's rules (CDK's custom resource empties them);
        # the network interfaces of a Lambda in the VPC; and the answer to a task token (no resource type).
        _declaracion(sid="SinArnDelLimite", actions=[
            "logs:DescribeLogGroups", "logs:DescribeLogStreams",
            "logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery", "logs:DeleteLogDelivery",
            "logs:ListLogDeliveries", "logs:PutResourcePolicy", "logs:DescribeResourcePolicies",
            "xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets",
            "cloudformation:Describe*", "cloudformation:Get*", "cloudformation:List*",
            "ec2:DescribeSecurityGroups", "ec2:RevokeSecurityGroupIngress", "ec2:RevokeSecurityGroupEgress",
            "ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface",
            "ec2:AssignPrivateIpAddresses", "ec2:UnassignPrivateIpAddresses",
            "states:SendTaskSuccess", "states:SendTaskFailure"], resources=["*"]),
        # KMS only through DynamoDB in this Region: the stack key encrypts the project's tables (activity 6).
        _declaracion(sid="KmsParaDynamoDelLimite", actions=[
            "kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey*", "kms:DescribeKey"],
            resources=[f"arn:{Aws.PARTITION}:kms:{REGION}:{Aws.ACCOUNT_ID}:key/*"],
            conditions={"StringEquals": {"kms:ViaService": f"dynamodb.{REGION}.amazonaws.com"}}),
        # Invoking the project's functions (the questions function starts the agent asynchronously, activity 6).
        _declaracion(sid="InvocarFuncionesDelLimite", actions=["lambda:InvokeFunction"],
                     resources=[f"arn:{Aws.PARTITION}:lambda:{REGION}:{Aws.ACCOUNT_ID}:function:semana19-*"]),
        # DynamoDB for the project's tables only (the tables' own roles get their exact table in their identity policy).
        _declaracion(sid="DynamoDBDelLimite", actions=[
            "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"],
            resources=[f"arn:{Aws.PARTITION}:dynamodb:{REGION}:{Aws.ACCOUNT_ID}:table/semana19-*"]),
        _declaracion(sid="CdkAssumeRoles", actions=["sts:AssumeRole"],
                     resources=[arn_iam(f"role/{PREFIJO_ROLES_CDK}*")]),
        # Key use only when the call comes through Bedrock or AgentCore in this Region (kms:ViaService): the guardrail
        # creator and the comparison agent (bedrock), the gateway encrypted with the base key (activity 7, bedrock-agentcore).
        _declaracion(sid="KmsParaBedrockDelLimite", actions=[
            "kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey*", "kms:DescribeKey", "kms:CreateGrant"],
            resources=[f"arn:{Aws.PARTITION}:kms:{REGION}:{Aws.ACCOUNT_ID}:key/*"],
            conditions={"StringEquals": {"kms:ViaService": [f"bedrock.{REGION}.amazonaws.com",
                                                            f"bedrock-agentcore.{REGION}.amazonaws.com"]}}),
        # Ceiling for the guardrail creator's role (stack semana19-ia): Guardrail actions only, in this account and Region.
        _declaracion(sid="GuardrailDelLimite", actions=[
            "bedrock:CreateGuardrail", "bedrock:UpdateGuardrail", "bedrock:DeleteGuardrail", "bedrock:GetGuardrail",
            "bedrock:CreateGuardrailVersion", "bedrock:TagResource"],
            resources=[f"arn:{Aws.PARTITION}:bedrock:{REGION}:{Aws.ACCOUNT_ID}:guardrail/*",
                       f"arn:{Aws.PARTITION}:bedrock:{REGION}:{Aws.ACCOUNT_ID}:guardrail-profile/us.guardrail.v1:0"]),
        _declaracion(sid="AdjuntarPoliticasAlRolDeDespliegue", actions=["iam:AttachRolePolicy", "iam:DetachRolePolicy"],
                     resources=[ARN_DESPLIEGUE]),
        # Techo de los roles de datos: lo que la KB (semana19-kb) y el cargador necesitan. Cada statement
        # se acota por prefijo o por servicio; la política propia del rol decide el resto.
        _declaracion(sid="DocsDatosLeer", actions=["s3:GetObject"],
                     resources=[f"arn:{Aws.PARTITION}:s3:::semana19-datos*/*"]),
        _declaracion(sid="DocsDatosListar", actions=["s3:ListBucket"],
                     resources=[f"arn:{Aws.PARTITION}:s3:::semana19-datos*"]),
        _declaracion(sid="DocsDatosEscribir", actions=["s3:PutObject"],
                     resources=[f"arn:{Aws.PARTITION}:s3:::semana19-datos*/docs/*"]),
        _declaracion(sid="IndiceKbDatos", actions=["s3vectors:GetIndex", "s3vectors:PutVectors", "s3vectors:GetVectors",
                                                   "s3vectors:DeleteVectors", "s3vectors:QueryVectors",
                                                   "s3vectors:ListVectors"],
                     resources=[f"arn:{Aws.PARTITION}:s3vectors:{REGION}:{Aws.ACCOUNT_ID}:bucket/semana19-kb-*/index/*"]),
        _declaracion(sid="EmbeberConTitan", actions=["bedrock:InvokeModel"],
                     resources=[f"arn:{Aws.PARTITION}:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0"]),
        _declaracion(sid="SecretoBdLeer", actions=["secretsmanager:GetSecretValue"],
                     resources=[f"arn:{Aws.PARTITION}:secretsmanager:{REGION}:{Aws.ACCOUNT_ID}:secret:semana19datos*"]),
        _declaracion(sid="CifrarSoloViaS3YSecretos", actions=["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey*",
                                                              "kms:DescribeKey"], resources=["*"],
                     conditions={"StringEquals": {"kms:ViaService": [f"s3.{REGION}.amazonaws.com",
                                                                     f"secretsmanager.{REGION}.amazonaws.com"]}}),
        # The loader's log group is created by Lambda on the first run; without this the boundary blocks it and
        # the function's errors are invisible. Scoped to the functions of the datos stack.
        _declaracion(sid="LogsDeLaLambdaDatos", actions=["logs:CreateLogGroup"],
                     resources=[f"arn:{Aws.PARTITION}:logs:{REGION}:{Aws.ACCOUNT_ID}:log-group:/aws/lambda/semana19-datos*"]),
        # Ceiling of the computo roles (activity 6): what the agent, the tools, the writer and the approval flow call.
        # Without these the boundary denies the call even though the role's own policy allows it (verified with
        # iam simulate-principal-policy on the deployed roles: implicitDeny, AllowedByPermissionsBoundary=False).
        # The comparison agent (Bedrock Agents, activity 7) also streams and reads the profile and the model
        # (bedrock/latest/userguide/agents-permissions.html, inference profiles).
        _declaracion(sid="ModeloDelAgenteDelLimite", actions=[
            "bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:GetInferenceProfile",
            "bedrock:GetFoundationModel"], resources=arns_modelo_del_agente()),
        _declaracion(sid="GuardrailDelAgenteDelLimite", actions=["bedrock:ApplyGuardrail"],
                     resources=[f"arn:{Aws.PARTITION}:bedrock:{REGION}:{Aws.ACCOUNT_ID}:guardrail/*",
                                *arns_perfil_guardrail()]),
        _declaracion(sid="ConectarBdDelLimite", actions=["rds-db:connect"],
                     resources=[f"arn:{Aws.PARTITION}:rds-db:{REGION}:{Aws.ACCOUNT_ID}:dbuser:*/{u}"
                                for u in USUARIOS_BD_COMPUTO]),
        _declaracion(sid="ArrancarAprobacionDelLimite", actions=["states:StartExecution"],
                     resources=[f"arn:{Aws.PARTITION}:states:{REGION}:{Aws.ACCOUNT_ID}:stateMachine:semana19-*"]),
        # The gateway's role evaluates the Cedar policies (activity 7): both actions need the engine and the gateway
        # (bedrock-agentcore/latest/devguide/policy-permissions.html).
        _declaracion(sid="PolicyDelGatewayDelLimite", actions=[
            "bedrock-agentcore:AuthorizeAction", "bedrock-agentcore:PartiallyAuthorizeActions",
            "bedrock-agentcore:GetPolicyEngine"],
            resources=[f"arn:{Aws.PARTITION}:bedrock-agentcore:{REGION}:{Aws.ACCOUNT_ID}:policy-engine/semana19*",
                       f"arn:{Aws.PARTITION}:bedrock-agentcore:{REGION}:{Aws.ACCOUNT_ID}:gateway/semana19-*"]),
    ]


# Destination Regions of the US cross-Region profiles (model and guardrail), as `aws bedrock get-inference-profile`
# lists them for the agent's model and as the guardrail-profile permissions page lists them for us.guardrail.v1:0.
REGIONES_PERFIL_US = ("us-east-1", "us-east-2", "us-west-2")
# The database users the computo functions connect as (IAM auth): the tools read, the writer writes purchase_orders.
USUARIOS_BD_COMPUTO = ("copilot_ro", "order_writer")


def arns_modelo_del_agente() -> list[str]:
    """The agent's inference profile in this account and its foundation model in each destination Region."""
    import sys as _sys
    if str(Path(__file__).resolve().parents[2]) not in _sys.path:
        _sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ia.config import MODELO_ID  # the one place the model id lives (ia/config.py)
    fundacion = MODELO_ID.split(".", 1)[1]
    return [f"arn:{Aws.PARTITION}:bedrock:{REGION}:{Aws.ACCOUNT_ID}:inference-profile/{MODELO_ID}",
            *[f"arn:{Aws.PARTITION}:bedrock:{r}::foundation-model/{fundacion}" for r in REGIONES_PERFIL_US]]


def arns_perfil_guardrail() -> list[str]:
    """ApplyGuardrail with a cross-Region guardrail is also authorized against the profile in each destination Region."""
    return [f"arn:{Aws.PARTITION}:bedrock:{r}:{Aws.ACCOUNT_ID}:guardrail-profile/us.guardrail.v1:0"
            for r in REGIONES_PERFIL_US]


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


def politica_ejecucion_ia() -> list[iam.PolicyStatement]:
    """Second execution policy of the bootstrap, for the stacks semana19-ia (prompts, guardrail creator). Split from
    semana19-cfn-exec, which exceeded the 6,144-character managed policy limit. Same statements, same permissions."""
    return [
        # Prompt Management for the agent's system prompt (stack semana19-ia): create, version and read prompts of this account.
        _declaracion(sid="PromptsDelAgentePorCfn", actions=[
            "bedrock:CreatePrompt", "bedrock:CreatePromptVersion", "bedrock:GetPrompt", "bedrock:UpdatePrompt",
            "bedrock:DeletePrompt", "bedrock:TagResource", "bedrock:UntagResource", "bedrock:ListTagsForResource"],
            resources=[f"arn:{Aws.PARTITION}:bedrock:{REGION}:{Aws.ACCOUNT_ID}:prompt/*"]),
        # Through Bedrock (prompts, the comparison agent) and AgentCore (the gateway and its policy engine, activity 7):
        # creating a resource encrypted with the base key needs the caller's grant and data key (gateway-encryption).
        _declaracion(sid="LlaveDeLosPromptsPorCfn", actions=["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey*",
                                                             "kms:DescribeKey", "kms:CreateGrant"],
                     resources=[f"arn:{Aws.PARTITION}:kms:{REGION}:{Aws.ACCOUNT_ID}:key/*"],
                     conditions={"StringEquals": {"kms:ViaService": [f"bedrock.{REGION}.amazonaws.com",
                                                                     f"bedrock-agentcore.{REGION}.amazonaws.com"]}}),
        # The guardrail creator's function runs with its role (stack semana19-ia): CloudFormation passes it to Lambda.
        _declaracion(sid="PasarRolDelCreadorDeGuardrail", actions=["iam:PassRole"],
                     resources=[arn_iam("role/semana19-ia-*")],
                     conditions={"StringEquals": {"iam:PassedToService": "lambda.amazonaws.com"}}),
        # The guardrail creator's role (stack semana19-ia): its inline policies and deletion, same shape as the base.
        _declaracion(sid="PoliticasYAdjuntosDelRolDeIa", actions=[
            "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy", "iam:ListRolePolicies",
            "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:ListAttachedRolePolicies", "iam:ListRoleTags"],
            resources=[arn_iam("role/semana19-ia-*")]),
        _declaracion(sid="BorrarRolDeIa", actions=["iam:DeleteRole", "iam:GetRole"],
                     resources=[arn_iam("role/semana19-ia-*")]),
    ]


def politica_ejecucion_computo() -> list[iam.PolicyStatement]:
    """Fourth execution policy of the bootstrap, for stack semana19-computo (Cognito, token table, approval state machine,
    HTTP API). Split out because the stack's calls do not fit the 6,144-character limit of the other policies."""
    region_api = f"arn:{Aws.PARTITION}:apigateway:{REGION}::"
    return [
        # HTTP API (API Gateway v2): the create call has no ARN yet, so the path is the only resource.
        _declaracion(sid="ApiHttpPorCfn", actions=[
            "apigateway:GET", "apigateway:POST", "apigateway:PUT", "apigateway:PATCH", "apigateway:DELETE",
            "apigateway:TagResource", "apigateway:UntagResource"],
            resources=[f"{region_api}/apis", f"{region_api}/apis/*", f"{region_api}/tags/*"]),
        # Cognito pool, its client, resource servers and groups: created by CloudFormation, no ARN before creation.
        _declaracion(sid="CognitoPorCfn", actions=[
            "cognito-idp:CreateUserPool", "cognito-idp:UpdateUserPool", "cognito-idp:DeleteUserPool",
            "cognito-idp:DescribeUserPool", "cognito-idp:SetUserPoolMfaConfig", "cognito-idp:GetUserPoolMfaConfig",
            "cognito-idp:CreateUserPoolClient", "cognito-idp:UpdateUserPoolClient", "cognito-idp:DeleteUserPoolClient",
            "cognito-idp:DescribeUserPoolClient", "cognito-idp:CreateResourceServer", "cognito-idp:UpdateResourceServer",
            "cognito-idp:DeleteResourceServer", "cognito-idp:CreateGroup", "cognito-idp:UpdateGroup",
            "cognito-idp:DeleteGroup", "cognito-idp:GetGroup", "cognito-idp:TagResource", "cognito-idp:UntagResource",
            "cognito-idp:ListTagsForResource"],
            resources=["*"]),
        # Token table (DynamoDB) with the stack key: named by CloudFormation from the stack name.
        _declaracion(sid="TablaDeTokensPorCfn", actions=[
            "dynamodb:CreateTable", "dynamodb:UpdateTable", "dynamodb:DeleteTable", "dynamodb:DescribeTable",
            "dynamodb:UpdateTimeToLive", "dynamodb:DescribeTimeToLive", "dynamodb:TagResource",
            "dynamodb:UntagResource", "dynamodb:ListTagsOfResource", "dynamodb:DescribeContinuousBackups"],
            resources=[f"arn:{Aws.PARTITION}:dynamodb:{REGION}:{Aws.ACCOUNT_ID}:table/semana19-*"]),
        _declaracion(sid="LlaveDeLaTablaPorCfn", actions=["kms:CreateGrant", "kms:ListGrants", "kms:DescribeKey"],
                     resources=["*"],
                     conditions={"StringEquals": {"kms:ViaService": f"dynamodb.{REGION}.amazonaws.com"}}),
        # Roles of computo (names start with semana19-computo-): CloudFormation reads and writes their inline and attached
        # policies. Creation still needs the boundary (RolesConLimite); these calls carry no boundary key, so they are
        # listed here, limited to this stack's role names. They cannot change the boundary.
        _declaracion(sid="RolesDeComputoPorCfn", actions=[
            "iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:ListRoleTags",
            "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:AttachRolePolicy", "iam:DetachRolePolicy",
            "iam:DeleteRole", "iam:UpdateAssumeRolePolicy", "iam:TagRole", "iam:UntagRole"],
            resources=[arn_iam("role/semana19-computo-*")]),
        # Access logs of the HTTP API: API Gateway enables delivery to the log group. Delivery actions have no ARN.
        _declaracion(sid="EntregaDeLogsDeApiPorCfn", actions=[
            "logs:CreateLogDelivery", "logs:DeleteLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery",
            "logs:ListLogDeliveries", "logs:PutResourcePolicy", "logs:DescribeResourcePolicies"],
            resources=["*"]),
        # Approval state machine (Step Functions) named semana19-aprobacion.
        _declaracion(sid="MaquinaDeAprobacionPorCfn", actions=[
            "states:CreateStateMachine", "states:UpdateStateMachine", "states:DeleteStateMachine",
            "states:DescribeStateMachine", "states:TagResource", "states:UntagResource", "states:ListTagsForResource"],
            resources=[f"arn:{Aws.PARTITION}:states:{REGION}:{Aws.ACCOUNT_ID}:stateMachine:semana19-*"]),
        # The roles of computo's functions and state machine are created with the boundary (RolesConLimite in the
        # first policy); CloudFormation only passes them to Lambda and Step Functions.
        _declaracion(sid="PasarRolesDeComputoAFuncionesYMaquina", actions=["iam:PassRole"],
                     resources=[arn_iam("role/semana19-*")],
                     conditions={"StringEquals": {"iam:PassedToService": ["lambda.amazonaws.com",
                                                                         "states.amazonaws.com"]}}),
    ]


def politica_ejecucion_agentes() -> list[iam.PolicyStatement]:
    """Fifth execution policy of the bootstrap (activity 7): the AgentCore Gateway with its Policy engine (stack
    semana19-gateway) and the Bedrock Agents comparison (stack semana19-agentes-comparacion). The roles of both stacks
    are created with the boundary by RolesConLimite (first policy); the Lambda permission for the agent by
    FuncionesDeCustomResourceDelProyecto. Actions from bedrock-agentcore/latest/devguide/policy-permissions.html and
    gateway-prerequisites-permissions.html; Bedrock Agents resource types from the Service Authorization Reference."""
    agentcore = f"arn:{Aws.PARTITION}:bedrock-agentcore:{REGION}:{Aws.ACCOUNT_ID}"
    bedrock = f"arn:{Aws.PARTITION}:bedrock:{REGION}:{Aws.ACCOUNT_ID}"
    return [
        # The gateway, its target and its workload identity (named after the gateway). InvokeGateway: CreatePolicy
        # validates the Cedar actions against the gateway's tools with the caller's identity.
        _declaracion(sid="GatewayPorCfn", actions=[
            "bedrock-agentcore:CreateGateway", "bedrock-agentcore:UpdateGateway", "bedrock-agentcore:GetGateway",
            "bedrock-agentcore:DeleteGateway", "bedrock-agentcore:InvokeGateway",
            "bedrock-agentcore:CreateGatewayTarget", "bedrock-agentcore:UpdateGatewayTarget",
            "bedrock-agentcore:GetGatewayTarget", "bedrock-agentcore:DeleteGatewayTarget",
            "bedrock-agentcore:ListGatewayTargets", "bedrock-agentcore:SynchronizeGatewayTargets",
            "bedrock-agentcore:ManageResourceScopedPolicy", "bedrock-agentcore:ManageAdminPolicy",
            "bedrock-agentcore:CreateWorkloadIdentity", "bedrock-agentcore:GetWorkloadIdentity",
            "bedrock-agentcore:UpdateWorkloadIdentity", "bedrock-agentcore:DeleteWorkloadIdentity",
            "bedrock-agentcore:TagResource", "bedrock-agentcore:UntagResource",
            "bedrock-agentcore:ListTagsForResource"],
            resources=[f"{agentcore}:*gateway*"]),
        _declaracion(sid="MotorDePoliticasPorCfn", actions=[
            "bedrock-agentcore:CreatePolicyEngine", "bedrock-agentcore:UpdatePolicyEngine",
            "bedrock-agentcore:GetPolicyEngine", "bedrock-agentcore:DeletePolicyEngine",
            "bedrock-agentcore:GetPolicyEngineSummary",
            "bedrock-agentcore:CreatePolicy", "bedrock-agentcore:UpdatePolicy", "bedrock-agentcore:GetPolicy",
            "bedrock-agentcore:DeletePolicy", "bedrock-agentcore:ListPolicies", "bedrock-agentcore:GetPolicySummary",
            "bedrock-agentcore:ListPolicySummaries",
            "bedrock-agentcore:TagResource", "bedrock-agentcore:UntagResource",
            "bedrock-agentcore:ListTagsForResource"],
            resources=[f"{agentcore}:policy-engine/*"]),
        # Bedrock Agents: CreateAgent has no resource type (Service Authorization Reference); the rest take the agent.
        _declaracion(sid="CrearAgentePorCfn", actions=["bedrock:CreateAgent"], resources=["*"]),
        _declaracion(sid="AgentePorCfn", actions=[
            "bedrock:UpdateAgent", "bedrock:GetAgent", "bedrock:DeleteAgent", "bedrock:PrepareAgent",
            "bedrock:CreateAgentActionGroup", "bedrock:UpdateAgentActionGroup", "bedrock:GetAgentActionGroup",
            "bedrock:DeleteAgentActionGroup", "bedrock:ListAgentActionGroups",
            "bedrock:CreateAgentAlias", "bedrock:UpdateAgentAlias", "bedrock:GetAgentAlias", "bedrock:DeleteAgentAlias",
            "bedrock:ListAgentAliases", "bedrock:ListAgentVersions", "bedrock:GetAgentVersion",
            "bedrock:DeleteAgentVersion", "bedrock:TagResource", "bedrock:UntagResource",
            "bedrock:ListTagsForResource"],
            resources=[f"{bedrock}:agent/*", f"{bedrock}:agent-alias/*"]),
        # The agent's model and guardrail are read when the agent is created and prepared.
        _declaracion(sid="ModeloYGuardrailDelAgentePorCfn", actions=[
            "bedrock:GetInferenceProfile", "bedrock:GetFoundationModel", "bedrock:GetGuardrail"],
            resources=[*arns_modelo_del_agente(), f"{bedrock}:guardrail/*"]),
        _declaracion(sid="PasarRolesAAgentCoreYBedrock", actions=["iam:PassRole"],
                     resources=[arn_iam("role/semana19-*")],
                     conditions={"StringEquals": {"iam:PassedToService": ["bedrock-agentcore.amazonaws.com",
                                                                         "bedrock.amazonaws.com"]}}),
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
        # The attachment writes the connection details into the generated secret (PutSecretValue); same prefix.
        _declaracion(sid="EscribirSecretoDeLaBdPorCfn", actions=["secretsmanager:PutSecretValue",
                                                                 "secretsmanager:UpdateSecretVersionStage"],
                     resources=[f"arn:{Aws.PARTITION}:secretsmanager:{REGION}:{Aws.ACCOUNT_ID}:secret:semana19datos*"]),
        # RDS reads the generated secret to apply the master password; the secret name starts with semana19datos.
        _declaracion(sid="LeerSecretoDeLaBdPorCfn", actions=["secretsmanager:GetSecretValue"],
                     resources=[f"arn:{Aws.PARTITION}:secretsmanager:{REGION}:{Aws.ACCOUNT_ID}:secret:semana19datos*"]),
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
        ejecucion_ia = iam.ManagedPolicy(self, "EjecucionCfnIa", managed_policy_name=EJECUCION_CFN_IA,
                                         statements=politica_ejecucion_ia(),
                                         description="Third CloudFormation execution policy: stacks semana19-ia (prompts, guardrail creator), split from semana19-cfn-exec.")

        ejecucion_computo = iam.ManagedPolicy(
            self, "EjecucionCfnComputo", managed_policy_name=EJECUCION_CFN_COMPUTO,
            statements=politica_ejecucion_computo(),
            description="Fourth CloudFormation execution policy: stack semana19-computo (approval workflow, Cognito, HTTP API).")

        ejecucion_agentes = iam.ManagedPolicy(
            self, "EjecucionCfnAgentes", managed_policy_name=EJECUCION_CFN_AGENTES,
            statements=politica_ejecucion_agentes(),
            description="Fifth CloudFormation execution policy: stacks semana19-gateway and semana19-agentes-comparacion (activity 7).")

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
            resources=[ARN_LIMITE, ARN_CONGELAR, ARN_EJECUCION_CFN, ARN_EJECUCION_CFN_DATOS, ARN_EJECUCION_CFN_IA,
                       ARN_EJECUCION_CFN_COMPUTO, ARN_EJECUCION_CFN_AGENTES]))
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

        suprimir_iam5(limite, ["LogsDelLimite", "SinArnDelLimite", "CdkAssumeRoles",
                               "DocsDatosLeer", "DocsDatosListar", "DocsDatosEscribir",
                               "IndiceKbDatos", "SecretoBdLeer", "CifrarSoloViaS3YSecretos",
                               "LogsDeLaLambdaDatos"])
        saltar_checkov(limite, {"CKV_AWS_111": "Lectura y revocación de SG por defecto sin ARN, y nombres por prefijo semana19-*/cdk-s19-*; ver EXCEPCIONES."})
        suprimir_iam5(congelar, ["NoCrearNiActualizarMientrasEsteActiva"])
        suprimir_iam5(ejecucion, ["VpcYRedes", "LlavesKms", "GruposDeLogs", "DescribirGruposDeLogs",
                                  "FuncionesDeCustomResourceDelProyecto", "RolesConLimite"])
        saltar_checkov(ejecucion_datos, {
            "CKV_AWS_111": "Creación de recursos del stack datos sin ARN previo (secreto, base, buckets, Knowledge Base); ver EXCEPCIONES.",
            "CKV_AWS_109": "Roles semana19-kb y semana19-datos-* sin condición de límite en las acciones de gestión: los roles se crean con semana19-limite (aplicado por el Aspect), y iam:PassRole solo hacia bedrock y lambda."})
        suprimir_iam5(ejecucion_datos, ["SecretoDeLaBdPorCfn", "ContrasenaGeneradaPorCfn", "LeerSecretoDeLaBdPorCfn", "EscribirSecretoDeLaBdPorCfn", "DescribirRdsPorCfn",
                                        "LlaveParaRdsYSecretos", "BaseDeDatosPostgresPorCfn", "BucketDocsKbPorCfn",
                                        "VectoresKbPorCfn", "KnowledgeBasePorCfn", "CrearKnowledgeBasePorCfn",
                                        "RolesDelDatosPorCfn", "PasarRolesDelDatosAKbYLambda", "ConcurrenciaDelCargador"])
        saltar_checkov(ejecucion, {
            "CKV_AWS_111": "Creación de recursos del proyecto sin ARN previo (VPC, llaves, grupos); ver EXCEPCIONES.",
            "CKV_AWS_109": "Gestión de roles limitada a nombres semana19-* y obligatoriamente con el límite (condición iam:PermissionsBoundary); ver EXCEPCIONES."})
        suprimir_iam5(ejecucion_ia, ["PromptsDelAgentePorCfn", "LlaveDeLosPromptsPorCfn", "PasarRolDelCreadorDeGuardrail",
                                     "PoliticasYAdjuntosDelRolDeIa", "BorrarRolDeIa"])
        suprimir_iam5(ejecucion_computo, ["ApiHttpPorCfn", "CognitoPorCfn", "TablaDeTokensPorCfn", "LlaveDeLaTablaPorCfn",
                                          "RolesDeComputoPorCfn",
                                          "EntregaDeLogsDeApiPorCfn",
                                          "MaquinaDeAprobacionPorCfn", "PasarRolesDeComputoAFuncionesYMaquina"])
        saltar_checkov(ejecucion_computo, {
            "CKV_AWS_111": "Escritura sobre '*' solo donde AWS no admite ARN previo: creación del pool de Cognito (CognitoPorCfn), "
                           "entrega de logs de la HTTP API (EntregaDeLogsDeApiPorCfn) y grants de la llave vía DynamoDB "
                           "(LlaveDeLaTablaPorCfn, con kms:ViaService); ver EXCEPCIONES."})
        suprimir_iam5(ejecucion_agentes, ["GatewayPorCfn", "MotorDePoliticasPorCfn", "CrearAgentePorCfn", "AgentePorCfn",
                                          "ModeloYGuardrailDelAgentePorCfn", "PasarRolesAAgentCoreYBedrock"])
        saltar_checkov(ejecucion_agentes, {
            "CKV_AWS_111": "CreateAgent sin tipo de recurso (Service Authorization Reference) y recursos de AgentCore sin ID previo; ver EXCEPCIONES."})
        suprimir_iam5(despliegue, ["AsumirRolesCdk", "LeerCloudFormation", "CrearRolesSoloConLimite",
                                   "NoQuitarNiCambiarElLimite"])
        cdk.CfnOutput(self, "ArnLimite", value=limite.managed_policy_arn)
        cdk.CfnOutput(self, "ArnDespliegue", value=despliegue.role_arn)
        cdk.CfnOutput(self, "ArnCongelar", value=congelar.managed_policy_arn)
        cdk.CfnOutput(self, "ArnEjecucionCfn", value=ejecucion.managed_policy_arn)
        cdk.CfnOutput(self, "ArnEjecucionCfnDatos", value=ejecucion_datos.managed_policy_arn)
        cdk.CfnOutput(self, "ArnEjecucionCfnIa", value=ejecucion_ia.managed_policy_arn)
        cdk.CfnOutput(self, "ArnEjecucionCfnComputo", value=ejecucion_computo.managed_policy_arn)
        cdk.CfnOutput(self, "ArnEjecucionCfnAgentes", value=ejecucion_agentes.managed_policy_arn)


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
                # Step Functions log delivery (state machine logs to an encrypted group) is performed by the delivery service.
                _declaracion(sid="DeliveryDeLogsDescifra", actions=["kms:Decrypt"], resources=["*"],
                             principals=[iam.ServicePrincipal("delivery.logs.amazonaws.com")]),
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
        self.sg_endpoints = sg_endpoints

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
        # S3 is reached through the gateway endpoint, which routes by the managed prefix list (not by a public IP).
        # Without this egress rule the loader hangs on the first document upload. pl-63a5400a = com.amazonaws.us-east-1.s3.
        sg_cargador.add_egress_rule(ec2.Peer.prefix_list("pl-63a5400a"), ec2.Port.tcp(443), "HTTPS a S3 (endpoint gateway)")

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
        self.sg_bd = sg_bd
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
        # No bedrock-agent endpoint: its private DNS conflicts with the VPC (AWS rejected it). The KB ingestion job
        # is started from the operator terminal (control-plane call, not database access); see semana-19/actividad-4.md.

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


def _definicion_guardrail() -> dict:
    """The Guardrail definition (semana-19/guardrail/definicion.py), loaded from its file."""
    import importlib.util
    ruta = Path(__file__).resolve().parents[2] / "guardrail" / "definicion.py"
    spec = importlib.util.spec_from_file_location("definicion_guardrail", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.definicion_guardrail("semana19-legacybridge")


def _cargar_hoja(nombre: str):
    """A module under semana-19/ia (config and prompt texts), loaded by path like the definition of the guardrail."""
    import importlib.util
    ruta = Path(__file__).resolve().parents[2] / "ia" / nombre
    spec = importlib.util.spec_from_file_location(f"ia_{ruta.stem}", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class Ia(Stack):
    """Activity 5: the Guardrail semana19-legacybridge and one published version, encrypted with the base key.

    CloudFormation's AWS::Bedrock::Guardrail has no tierConfig, so a custom resource (semana-19/guardrail/handler.py)
    creates the Guardrail with the definition of semana-19/guardrail/definicion.py: content filters and topics on the
    STANDARD tier (GuardrailChecks, cross-Region through the US guardrail profile), grounding on CLASSIC. The function
    has its own role (only Guardrail actions and the base key), outside the VPC, with its log group encrypted.
    """

    def __init__(self, scope: Construct, id: str, *, llave: kms.IKey, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        grupo = logs.LogGroup(
            self, "LogsCreadorGuardrail", log_group_name=f"{PREFIJO_LOGS}ia/creador-guardrail",
            retention=logs.RetentionDays.ONE_WEEK, encryption_key=llave, removal_policy=RemovalPolicy.DESTROY)
        creador = lambda_.Function(
            self, "CreadorGuardrail", runtime=lambda_.Runtime.PYTHON_3_13, handler="handler.handler",
            code=lambda_.Code.from_asset(str(Path(__file__).resolve().parents[2] / "guardrail"), exclude=[
                "comparar_determinista.py", "prueba_viva.py", "tests", "__pycache__", "resultados"]),
            timeout=Duration.minutes(2), memory_size=256, reserved_concurrent_executions=1, log_group=grupo,
            description="Creates the semana19-legacybridge guardrail with its tier (custom resource, activity 5).")
        saltar_checkov(creador, {
            "CKV_AWS_117": "Custom resource del proyecto: la API de control de Bedrock es pública; fuera de la VPC por diseño.",
            "CKV_AWS_116": "Custom resource: CloudFormation reintenta y reporta el fallo en la respuesta; no hay cola que vigilar.",
        })
        creador.add_to_role_policy(_declaracion(
            sid="GuardrailEnBedrock", actions=[
                "bedrock:CreateGuardrail", "bedrock:UpdateGuardrail", "bedrock:DeleteGuardrail",
                "bedrock:GetGuardrail", "bedrock:CreateGuardrailVersion", "bedrock:TagResource"],
            resources=[f"arn:{Aws.PARTITION}:bedrock:{REGION}:{Aws.ACCOUNT_ID}:guardrail/*"]))
        # CreateGuardrail with a cross-Region config is also authorized against the guardrail profile (account-scoped ARN).
        perfil = _definicion_guardrail()["crossRegionConfig"]["guardrailProfileIdentifier"]
        creador.add_to_role_policy(_declaracion(
            sid="PerfilEntreRegionesDelGuardrail", actions=["bedrock:CreateGuardrail", "bedrock:UpdateGuardrail"],
            resources=[f"arn:{Aws.PARTITION}:bedrock:{REGION}:{Aws.ACCOUNT_ID}:guardrail-profile/{perfil}"]))
        NagSuppressions.add_resource_suppressions(creador, [NagPackSuppression(
            id="AwsSolutions-L1", reason="Runtime Python 3.13, el más reciente aprobado para el laboratorio; el custom resource corre una vez por despliegue.")])
        NagSuppressions.add_resource_suppressions(creador.role, [NagPackSuppression(
            id="AwsSolutions-IAM4", reason="AWSLambdaBasicExecutionRole: escribir sus logs en su propio grupo; es la política administrada mínima para una función fuera de la VPC.")], apply_to_children=True)
        NagSuppressions.add_resource_suppressions(creador.role, [NagPackSuppression(
            id="AwsSolutions-IAM5", reason="Guardrail: CreateGuardrail recibe el nombre del guardrail, no su ARN; el ARN no existe antes de crearlo. Acotado a guardrail/* de esta cuenta y Región.")], apply_to_children=True)
        creador.add_to_role_policy(_declaracion(
            sid="LlaveDelGuardrail", actions=["kms:Decrypt", "kms:DescribeKey", "kms:GenerateDataKey", "kms:CreateGrant"],
            resources=[llave.key_arn]))
        recurso = cdk.CustomResource(
            self, "Guardrail", service_token=creador.function_arn,
            properties={**_definicion_guardrail(), "kmsKeyId": llave.key_arn})
        # Prompt Management: the agent's system prompt (ES and EN) with the model in one config value, encrypted with the
        # base key. Each change is a new version; the agent reads a pinned version (activity 6).
        modelo = _cargar_hoja("config.py").MODELO_ID
        textos = _cargar_hoja("prompts_sistema.py").PROMPTS
        for idioma, texto in textos.items():
            prompt = bedrock.CfnPrompt(
                self, f"Prompt{idioma.upper()}", name=f"semana19-sistema-{idioma}",
                description="System prompt of the LegacyBridge agent (activity 5).",
                customer_encryption_key_arn=llave.key_arn, default_variant="principal",
                variants=[bedrock.CfnPrompt.PromptVariantProperty(
                    name="principal", template_type="TEXT", model_id=modelo,
                    template_configuration=bedrock.CfnPrompt.PromptTemplateConfigurationProperty(
                        text=bedrock.CfnPrompt.TextPromptTemplateConfigurationProperty(
                            text=texto, input_variables=[bedrock.CfnPrompt.PromptInputVariableProperty(name="nombre_empresa")])))])
            version = bedrock.CfnPromptVersion(self, f"VersionPrompt{idioma.upper()}", prompt_arn=prompt.attr_arn,
                                               description=f"Version pinned by the agent: system prompt {idioma}.")
            cdk.CfnOutput(self, f"ArnVersionPrompt{idioma.upper()}", value=version.attr_arn)
        self.guardrail_id = recurso.get_att_string("GuardrailId")
        self.guardrail_version = recurso.get_att_string("Version")
        cdk.CfnOutput(self, "IdGuardrail", value=recurso.get_att_string("GuardrailId"))
        cdk.CfnOutput(self, "VersionGuardrail", value=recurso.get_att_string("Version"))


class Computo(Stack):
    """Activity 6: the approval workflow (Step Functions `semana19-aprobacion`), the approver's HTTP API (`semana19-api`) and
    the Cognito pool `semana19-usuarios` (Essentials, ADR 0009) with its pre-token trigger. The task token lives in a
    DynamoDB table encrypted with the stack key, with a TTL (ADR 0011). Opt-in with COMPUTO=1, so the foundation
    snapshots do not change. Synthesis only: nothing here is deployed by this activity without authorization.

    The approved request is written by the order writer (order_writer, inside the VPC) after the approval. The agent's
    compute and the tools Lambda are not in this stack.
    """

    def __init__(self, scope: Construct, id: str, *, llave: kms.IKey, red: ec2.Vpc, bd: rds.DatabaseInstance,
                 sg_bd: ec2.SecurityGroup, sg_endpoints: ec2.SecurityGroup, guardrail_id: str, guardrail_version: str,
                 **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        codigo = lambda_.Code.from_asset(str(Path(__file__).resolve().parents[2] / "computo"), exclude=["tests", "__pycache__"])

        def grupo(nombre: str) -> logs.LogGroup:
            return logs.LogGroup(self, f"Logs{nombre.replace('-', '')}", log_group_name=f"{PREFIJO_LOGS}computo/{nombre}",
                                 retention=logs.RetentionDays.ONE_WEEK, encryption_key=llave, removal_policy=RemovalPolicy.DESTROY)

        tabla = dynamodb.Table(
            self, "Tokens", partition_key=dynamodb.Attribute(name="id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST, encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=llave, time_to_live_attribute="expira", removal_policy=RemovalPolicy.DESTROY)

        pool = cognito.CfnUserPool(
            self, "Usuarios", user_pool_name="semana19-usuarios", user_pool_tier="ESSENTIALS",
            admin_create_user_config=cognito.CfnUserPool.AdminCreateUserConfigProperty(allow_admin_create_user_only=True),
            mfa_configuration="OFF",
            policies=cognito.CfnUserPool.PoliciesProperty(password_policy=cognito.CfnUserPool.PasswordPolicyProperty(
                minimum_length=12, require_lowercase=True, require_uppercase=True, require_numbers=True, require_symbols=True)))
        # Groups read by the pre-token trigger (computo/tokens.py); the test users are added to them by usuarios.py.
        # Separation of duties (Manuel's decision): compradores propose, the three approval groups decide up to their level.
        for id_grupo, nombre_grupo in (("GrupoAnalistas", "analistas"), ("GrupoCompradores", "compradores"),
                                       ("GrupoAprobadoresComprador", "aprobadores-comprador"),
                                       ("GrupoAprobadoresGerente", "aprobadores-gerente"),
                                       ("GrupoAprobadoresDirector", "aprobadores-director")):
            cognito.CfnUserPoolGroup(self, id_grupo, user_pool_id=pool.ref, group_name=nombre_grupo,
                                     description=f"Grupo {nombre_grupo} de LegacyBridge (activity 6)")
        servidor = cognito.CfnUserPoolResourceServer(
            self, "ServidorLegacyBridge", user_pool_id=pool.ref, identifier="legacybridge", name="LegacyBridge",
            scopes=[cognito.CfnUserPoolResourceServer.ResourceServerScopeTypeProperty(
                        scope_name="consultas", scope_description="Consultas del agente"),
                    cognito.CfnUserPoolResourceServer.ResourceServerScopeTypeProperty(
                        scope_name="aprobaciones", scope_description="Aprobaciones de órdenes")])
        servidor_legado = cognito.CfnUserPoolResourceServer(
            self, "ServidorLegado", user_pool_id=pool.ref, identifier="legado", name="Legado datos",
            scopes=[cognito.CfnUserPoolResourceServer.ResourceServerScopeTypeProperty(scope_name=nombre, scope_description=descripcion)
                    for nombre, descripcion in (("leer", "Lectura del esquema legado"), ("proveedores", "Proveedores"),
                                                ("ventas", "Ventas"), ("compras_proponer", "Proponer órdenes de compra"))])
        cliente = cognito.CfnUserPoolClient(
            self, "ClienteApp", user_pool_id=pool.ref, client_name="semana19-app", generate_secret=False,
            allowed_o_auth_flows=["code"], allowed_o_auth_flows_user_pool_client=True,
            allowed_o_auth_scopes=["openid", "email", "profile", "legacybridge/consultas", "legacybridge/aprobaciones",
                                   "legado/leer", "legado/proveedores", "legado/ventas", "legado/compras_proponer"],
            callback_ur_ls=["http://localhost:8080/callback"],  # GAP: managed login steps not verified (ADR 0010)
            supported_identity_providers=["COGNITO"], prevent_user_existence_errors="ENABLED",
            # Lab tests (activity 6): admin password login from the terminal, for the two test users only. Revert by removing it.
            explicit_auth_flows=["ALLOW_ADMIN_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"])
        cliente.node.add_dependency(servidor)
        cliente.node.add_dependency(servidor_legado)

        token_fn = lambda_.Function(
            self, "FuncionTokens", runtime=lambda_.Runtime.PYTHON_3_13, handler="tokens.handler", code=codigo,
            timeout=Duration.seconds(5), memory_size=128, log_group=grupo("tokens"),
            description="Pre-token generation V2: adds the LegacyBridge scopes from the groups (ADR 0009).")
        token_fn.add_permission("PermisoCognito", principal=iam.ServicePrincipal("cognito-idp.amazonaws.com"),
                                source_arn=pool.attr_arn)
        pool.lambda_config = cognito.CfnUserPool.LambdaConfigProperty(
            pre_token_generation_config=cognito.CfnUserPool.PreTokenGenerationConfigProperty(
                lambda_arn=token_fn.function_arn, lambda_version="V2_0"))

        registrar = lambda_.Function(
            self, "FuncionRegistrarToken", runtime=lambda_.Runtime.PYTHON_3_13, handler="aprobacion.handler_registrar",
            code=codigo, timeout=Duration.seconds(10), memory_size=128, log_group=grupo("registrar-token"),
            environment={"TABLA_TOKENS": tabla.table_name},
            description="Stores the approval task token in DynamoDB (activity 6). The token is never logged.")
        # Only what the handler does: put_item of the token row (no batch writes, no describe, no re-encrypt).
        tabla.grant(registrar, "dynamodb:PutItem")
        # DynamoDB calls kms:Decrypt on the table key for any item write too (live: PutItem denied without it).
        llave.grant(registrar.role, "kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey", "kms:DescribeKey")

        # Order writer (activity 6): the only step that writes purchase_orders, as order_writer, inside the VPC.
        sg_escritor = ec2.SecurityGroup(
            self, "SgEscritor", vpc=red, allow_all_outbound=False,
            description="Order writer Lambda (activity 6): PostgreSQL 5432 and HTTPS to the endpoints only.")
        sg_escritor.add_egress_rule(ec2.Peer.security_group_id(sg_bd.security_group_id), ec2.Port.tcp(5432), "PostgreSQL")
        sg_escritor.add_egress_rule(ec2.Peer.security_group_id(sg_endpoints.security_group_id), ec2.Port.tcp(443),
                                    "HTTPS a los endpoints (logs)")
        ec2.CfnSecurityGroupIngress(
            self, "BdDesdeEscritor", group_id=sg_bd.security_group_id, ip_protocol="tcp", from_port=5432, to_port=5432,
            source_security_group_id=sg_escritor.security_group_id, description="PostgreSQL desde el escritor de ordenes")
        ec2.CfnSecurityGroupIngress(
            self, "EndpointsDesdeEscritor", group_id=sg_endpoints.security_group_id, ip_protocol="tcp", from_port=443,
            to_port=443, source_security_group_id=sg_escritor.security_group_id, description="HTTPS desde el escritor")
        codigo_escritor = lambda_.Code.from_asset(str(Path(__file__).resolve().parents[2]), exclude=[
            "infra/cdk", "cdk.out", "**/cdk.out", "tests", "**/tests", "**/__pycache__", "**/*.gz", "resultados", "video", "**/.secretos.env",
            ".venv", "**/.venv", ".build"])  # .build holds the agent package (its own asset)
        escritor = lambda_.Function(
            self, "FuncionEscritor", runtime=lambda_.Runtime.PYTHON_3_13, handler="computo.escritor.handler_escritor",
            code=codigo_escritor, timeout=Duration.seconds(30), memory_size=256, log_group=grupo("escritor"),
            vpc=red, vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[sg_escritor], environment={"HOST_BD": bd.db_instance_endpoint_address},
            description="Order writer (activity 6): writes the pending order and then the decision, as order_writer.")
        escritor.add_to_role_policy(_declaracion(
            sid="ConectarComoOrderWriter", actions=["rds-db:connect"],
            resources=[f"arn:{Aws.PARTITION}:rds-db:{REGION}:{Aws.ACCOUNT_ID}:dbuser:{bd.instance_resource_id}/order_writer"]))
        NagSuppressions.add_resource_suppressions(escritor.role, [NagPackSuppression(
            id="AwsSolutions-IAM4", reason="AWSLambdaVPCAccessExecutionRole: crear y borrar la interfaz de red de la Lambda en su subred y escribir sus logs; la política administrada mínima para una función dentro de una VPC.")])
        NagSuppressions.add_resource_suppressions(escritor, [NagPackSuppression(
            id="AwsSolutions-L1", reason="Runtime Python 3.13, el más reciente aprobado para el laboratorio (igual que el resto de funciones del stack).")])

        # Tools Lambda (activity 6b): read-only SQL as copilot_ro and the approval starter. Same VPC rules as the writer:
        # PostgreSQL to the database and HTTPS to the endpoints only. It is not invoked by any route in this change.
        sg_herramientas = ec2.SecurityGroup(
            self, "SgHerramientas", vpc=red, allow_all_outbound=False,
            description="Tools Lambda (activity 6b): PostgreSQL 5432 and HTTPS to the endpoints only.")
        sg_herramientas.add_egress_rule(ec2.Peer.security_group_id(sg_bd.security_group_id), ec2.Port.tcp(5432), "PostgreSQL")
        sg_herramientas.add_egress_rule(ec2.Peer.security_group_id(sg_endpoints.security_group_id), ec2.Port.tcp(443),
                                        "HTTPS a los endpoints (Step Functions, logs)")
        ec2.CfnSecurityGroupIngress(
            self, "BdDesdeHerramientas", group_id=sg_bd.security_group_id, ip_protocol="tcp", from_port=5432, to_port=5432,
            source_security_group_id=sg_herramientas.security_group_id, description="PostgreSQL desde la funcion de herramientas")
        ec2.CfnSecurityGroupIngress(
            self, "EndpointsDesdeHerramientas", group_id=sg_endpoints.security_group_id, ip_protocol="tcp", from_port=443,
            to_port=443, source_security_group_id=sg_herramientas.security_group_id, description="HTTPS desde la funcion de herramientas")
        # The tools run from the agent package (infra/paquete_agente.py): it carries the week 16 read-only guard
        # (semana-16/legacy-schema-audit), sqlglot, pg8000 and the RDS bundle at the paths the code computes.
        ruta_agente = Path(__file__).resolve().parents[2] / ".build" / "agente"
        if not (ruta_agente / "pydantic").is_dir() and os.environ.get("S19_SIN_DEPENDENCIAS") != "1":
            raise RuntimeError("falta el paquete del agente: ejecuta python3 semana-19/infra/paquete_agente.py antes de desplegar")
        herramientas = lambda_.Function(
            self, "FuncionHerramientas", runtime=lambda_.Runtime.PYTHON_3_13, handler="app.herramientas.construccion.handler_lambda",
            code=lambda_.Code.from_asset(str(ruta_agente)), timeout=Duration.seconds(30), memory_size=256, log_group=grupo("herramientas"),
            vpc=red, vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[sg_herramientas], reserved_concurrent_executions=2,
            environment={"HOST_BD": bd.db_instance_endpoint_address},
            description="Tools (activity 6b): read-only SQL as copilot_ro and the start of the approval workflow.")
        herramientas.add_to_role_policy(_declaracion(
            sid="ConectarComoCopilotRo", actions=["rds-db:connect"],
            resources=[f"arn:{Aws.PARTITION}:rds-db:{REGION}:{Aws.ACCOUNT_ID}:dbuser:{bd.instance_resource_id}/copilot_ro"]))
        NagSuppressions.add_resource_suppressions(herramientas.role, [NagPackSuppression(
            id="AwsSolutions-IAM4", reason="AWSLambdaVPCAccessExecutionRole: crear y borrar la interfaz de red de la Lambda en su subred y escribir sus logs; la política administrada mínima para una función dentro de la VPC.")])
        NagSuppressions.add_resource_suppressions(herramientas, [NagPackSuppression(
            id="AwsSolutions-L1", reason="Runtime Python 3.13, el más reciente aprobado para el laboratorio (igual que el resto de funciones del stack).")])

        # Agent (activity 6b): the week 13 loop with the guardrail, the budget and the spans of week 17. Outside the VPC:
        # it calls Bedrock and the tools function through their public endpoints. Not behind any route yet.
        grupo_spans = grupo("spans")
        # Questions and answers (activity 6b): encrypted with the stack key, owner as a hash, expired by TTL after 7 days.
        tabla_consultas = dynamodb.Table(
            self, "Consultas", partition_key=dynamodb.Attribute(name="id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST, encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=llave, time_to_live_attribute="expira", removal_policy=RemovalPolicy.DESTROY)
        NagSuppressions.add_resource_suppressions(tabla_consultas, [NagPackSuppression(
            id="AwsSolutions-DDB3", reason="Consultas: respuestas efímeras con TTL de 7 días; la recuperación a un punto en el tiempo no aporta aquí y su costo no está verificado.")])
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from ia.config import MODELO_ID as modelo_con_perfil  # the one place the model id lives (ia/config.py)
        perfil_modelo = modelo_con_perfil                       # us.<family>...
        modelo_fundacion = modelo_con_perfil.split(".", 1)[1]    # the foundation model id behind the profile
        agente = lambda_.Function(
            self, "FuncionAgente", runtime=lambda_.Runtime.PYTHON_3_13, handler="app.consultas.worker.handler_lambda",
            code=lambda_.Code.from_asset(str(ruta_agente)), timeout=Duration.seconds(120), memory_size=512,
            log_group=grupo("agente"), reserved_concurrent_executions=2,
            environment={"FUNCION_HERRAMIENTAS": herramientas.function_name, "GUARDRAIL_ID": guardrail_id,
                         "GUARDRAIL_VERSION": guardrail_version, "GRUPO_SPANS": grupo_spans.log_group_name,
                         "S19_RUTA_SEMANA13": "/var/task/semana-13", "TABLA_CONSULTAS": tabla_consultas.table_name,
                         **entorno_del_camino()},
            description="Agent (activity 6b): answers a question with the week 13 loop, the guardrail and the budget.")
        agente.add_to_role_policy(_declaracion(
            sid="ModeloDeHaikuPorConverse", actions=["bedrock:InvokeModel"],
            resources=[f"arn:{Aws.PARTITION}:bedrock:{REGION}:{Aws.ACCOUNT_ID}:inference-profile/{perfil_modelo}",
                       f"arn:{Aws.PARTITION}:bedrock:*::foundation-model/{modelo_fundacion}"]))
        # The guardrail uses the cross-Region profile us.guardrail.v1:0: ApplyGuardrail needs the guardrail and the
        # profile in each destination Region (Bedrock guide, guardrail profile permissions).
        agente.add_to_role_policy(_declaracion(
            sid="GuardrailDelAgente", actions=["bedrock:ApplyGuardrail"],
            resources=[f"arn:{Aws.PARTITION}:bedrock:{REGION}:{Aws.ACCOUNT_ID}:guardrail/{guardrail_id}",
                       *arns_perfil_guardrail()]))
        agente.add_to_role_policy(_declaracion(
            sid="EscribirSpansDelAgente", actions=["logs:CreateLogStream", "logs:PutLogEvents"],
            resources=[grupo_spans.log_group_arn, f"{grupo_spans.log_group_arn}:*"]))
        agente.add_to_role_policy(iam.PolicyStatement(
            sid="InvocarHerramientas", actions=["lambda:InvokeFunction"], resources=[herramientas.function_arn]))
        agente.add_to_role_policy(_declaracion(
            sid="ActualizarConsultas", actions=["dynamodb:UpdateItem"], resources=[tabla_consultas.table_arn]))
        llave.grant(agente.role, "kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey")
        NagSuppressions.add_resource_suppressions(agente.role, [NagPackSuppression(
            id="AwsSolutions-IAM4", reason="AWSLambdaBasicExecutionRole: escribir sus logs en su propio grupo; la función está fuera de la VPC.")])
        NagSuppressions.add_resource_suppressions(agente, [NagPackSuppression(
            id="AwsSolutions-L1", reason="Runtime Python 3.13, el más reciente aprobado para el laboratorio (igual que el resto de funciones del stack).")])
        suprimir_iam5(agente.role, ["ModeloDeHaikuPorConverse", "EscribirSpansDelAgente"])

        # The workflow (spec: "writes the PENDING_APPROVAL request; waits for the task token"): the writer inserts the
        # pending order, the token is stored with the order's required level and requester, and after the approver's
        # decision the writer records it (APPROVED or REJECTED). Both writes run as order_writer.
        proponer = tasks.LambdaInvoke(
            self, "EscribirPropuesta", lambda_function=escritor,
            payload=sfn.TaskInput.from_object({"operacion": "proponer", "solicitud.$": "$.solicitud"}),
            payload_response_only=True, result_path="$.orden")
        espera = tasks.LambdaInvoke(
            self, "RegistrarToken", lambda_function=registrar,
            integration_pattern=sfn.IntegrationPattern.WAIT_FOR_TASK_TOKEN,
            payload=sfn.TaskInput.from_object({"id.$": "$.id", "token": sfn.JsonPath.task_token,
                                               "orden.$": "$.orden", "solicitud.$": "$.solicitud"}),
            result_path="$.decision", timeout=Duration.hours(24))
        decidir = tasks.LambdaInvoke(
            self, "EscribirDecision", lambda_function=escritor,
            payload=sfn.TaskInput.from_object({"operacion": "decidir", "po_id.$": "$.orden.po_id",
                                               "decision.$": "$.decision"}),
            payload_response_only=True, result_path="$.resultado")

        maquina = sfn.StateMachine(
            self, "Aprobacion", state_machine_name="semana19-aprobacion",
            definition_body=sfn.DefinitionBody.from_chainable(proponer.next(espera).next(decidir)),
            logs=sfn.LogOptions(destination=grupo("aprobacion"), level=sfn.LogLevel.ALL, include_execution_data=False),
            tracing_enabled=True, timeout=Duration.hours(24))

        aprobar = lambda_.Function(
            self, "FuncionAprobar", runtime=lambda_.Runtime.PYTHON_3_13, handler="aprobacion.handler_aprobar", code=codigo,
            timeout=Duration.seconds(10), memory_size=128, log_group=grupo("aprobar"),
            environment={"TABLA_TOKENS": tabla.table_name},
            description="Approver's decision: sends success or failure to the approval state machine (activity 6).")
        # Only what the handler does: get_item to read the token, delete_item after the decision (no scan, query or stream).
        tabla.grant(aprobar, "dynamodb:GetItem", "dynamodb:DeleteItem")
        llave.grant(aprobar.role, "kms:Decrypt", "kms:DescribeKey")
        # SendTaskSuccess takes no resource type (Service Authorization Reference): AWS evaluates it against '*', so a
        # state machine ARN here never matches. The task token itself names the execution. Approval and rejection both
        # go as SendTaskSuccess (the workflow's next state writes the decision), so SendTaskFailure is not granted.
        aprobar.add_to_role_policy(iam.PolicyStatement(
            sid="DecisionAlFlujo", actions=["states:SendTaskSuccess"], resources=["*"]))

        autorizador = apigwv2_auth.HttpJwtAuthorizer(
            "AutorizadorJwt", jwt_issuer=f"https://cognito-idp.{REGION}.amazonaws.com/{pool.ref}",
            jwt_audience=[cliente.ref], identity_source=["$request.header.Authorization"])
        api = apigwv2.HttpApi(self, "Api", api_name="semana19-api", create_default_stage=True)
        api.add_routes(
            path="/aprobaciones/{id}", methods=[apigwv2.HttpMethod.POST],
            integration=apigwv2_int.HttpLambdaIntegration("IntegracionAprobar", aprobar), authorizer=autorizador)
        etapa = api.default_stage.node.default_child
        etapa.access_log_settings = apigwv2.CfnStage.AccessLogSettingsProperty(
            destination_arn=grupo("api-acceso").log_group_arn,
            format=json.dumps({"requestId": "$context.requestId", "routeKey": "$context.routeKey",
                               "status": "$context.status", "responseLatency": "$context.responseLatency"}))
        for hijo in api.node.find_all():
            if isinstance(hijo, apigwv2.CfnRoute) and hijo.route_key == "POST /aprobaciones/{id}":
                hijo.authorization_scopes = ["legacybridge/aprobaciones"]

        NagSuppressions.add_resource_suppressions(tabla, [NagPackSuppression(
            id="AwsSolutions-DDB3", reason="Tokens de tarea: caducan por TTL a las 24 h y se borran al decidir; la recuperación a un punto en el tiempo no aporta nada aquí y su costo no está verificado.")])
        NagSuppressions.add_resource_suppressions(pool, [
            NagPackSuppression(id="AwsSolutions-COG2", reason="MFA desactivada en el laboratorio: usuarios de prueba creados por un administrador (ADR 0013); la decisión de MFA es de la actividad 8."),
            NagPackSuppression(id="AwsSolutions-COG8", reason="Feature plan Essentials por ADR 0009 (costo autorizado por Manuel); Plus no está autorizado y su costo no está verificado.")])
        for funcion in (token_fn, registrar, aprobar):
            NagSuppressions.add_resource_suppressions(funcion, [NagPackSuppression(
                id="AwsSolutions-L1", reason="Runtime Python 3.13, el más reciente aprobado para el laboratorio (igual que el creador del guardrail).")])
            NagSuppressions.add_resource_suppressions(funcion.role, [NagPackSuppression(
                id="AwsSolutions-IAM4", reason="AWSLambdaBasicExecutionRole: escribir sus logs en su propio grupo, la política administrada mínima para una función fuera de la VPC.")])
        NagSuppressions.add_resource_suppressions(registrar.role, [NagPackSuppression(
            id="AwsSolutions-IAM5", reason="PutItem en la tabla de tokens (y sus índices, grant de CDK) y uso de su llave KMS; ninguna otra tabla.")], apply_to_children=True)
        NagSuppressions.add_resource_suppressions(aprobar.role, [NagPackSuppression(
            id="AwsSolutions-IAM5", reason="Lectura y borrado en la tabla de tokens (y sus índices). | DecisionAlFlujo: " + EXCEPCIONES["DecisionAlFlujo"])], apply_to_children=True)
        NagSuppressions.add_resource_suppressions(maquina.role, [NagPackSuppression(
            id="AwsSolutions-IAM5", reason="Step Functions exige logs:*Log* sobre '*' para entregar sus logs (no admite un recurso más estrecho); la invocación a la Lambda de registro va acotada a su ARN.")], apply_to_children=True)
        # The approval state machine writes to its log group, which is encrypted with the stack key. The key policy does
        # not name this role, so the role gets the key actions in its own policy (the key policy's account root allows it).
        llave.grant(maquina.role, "kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey*", "kms:DescribeKey")
        herramientas.add_to_role_policy(iam.PolicyStatement(
            sid="ArrancarAprobacion", actions=["states:StartExecution"], resources=[maquina.state_machine_arn]))
        herramientas.add_environment("ARN_APROBACION", maquina.state_machine_arn)  # herramientas/construccion.REQUERIDAS

        # Questions (activity 6b): POST /consultas starts the agent asynchronously; GET /consultas/{id} reads the owner's answer.
        consultas_api = lambda_.Function(
            self, "FuncionConsultas", runtime=lambda_.Runtime.PYTHON_3_13, handler="app.consultas.api.handler_lambda",
            code=lambda_.Code.from_asset(str(ruta_agente)), timeout=Duration.seconds(10), memory_size=128,
            log_group=grupo("consultas"), reserved_concurrent_executions=5,
            environment={"TABLA_CONSULTAS": tabla_consultas.table_name, "FUNCION_AGENTE": agente.function_name},
            description="HTTP handler for POST /consultas and GET /consultas/{id} (activity 6b).")
        consultas_api.add_to_role_policy(_declaracion(
            sid="LeerEscribirConsultas", actions=["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"],
            resources=[tabla_consultas.table_arn]))
        llave.grant(consultas_api.role, "kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey", "kms:DescribeKey")
        consultas_api.add_to_role_policy(iam.PolicyStatement(
            sid="IniciarAgente", actions=["lambda:InvokeFunction"], resources=[agente.function_arn]))
        ruta_consulta = apigwv2_int.HttpLambdaIntegration("IntegracionConsultaCrear", consultas_api)
        ruta_lectura = apigwv2_int.HttpLambdaIntegration("IntegracionConsultaLeer", consultas_api)
        api.add_routes(path="/consultas", methods=[apigwv2.HttpMethod.POST], integration=ruta_consulta, authorizer=autorizador)
        api.add_routes(path="/consultas/{id}", methods=[apigwv2.HttpMethod.GET], integration=ruta_lectura, authorizer=autorizador)
        for hijo in api.node.find_all():
            if isinstance(hijo, apigwv2.CfnRoute) and hijo.route_key in ("POST /consultas", "GET /consultas/{id}"):
                hijo.authorization_scopes = ["legacybridge/consultas"]
        NagSuppressions.add_resource_suppressions(consultas_api.role, [NagPackSuppression(
            id="AwsSolutions-IAM4", reason="AWSLambdaBasicExecutionRole: escribir sus logs en su propio grupo; la función está fuera de la VPC.")])
        NagSuppressions.add_resource_suppressions(consultas_api, [NagPackSuppression(
            id="AwsSolutions-L1", reason="Runtime Python 3.13, el más reciente aprobado para el laboratorio (igual que el resto de funciones del stack).")])

        cdk.CfnOutput(self, "IdUsuarios", value=pool.ref)
        cdk.CfnOutput(self, "IdClienteApp", value=cliente.ref)
        cdk.CfnOutput(self, "UrlApi", value=api.api_endpoint)
        cdk.CfnOutput(self, "ArnAprobacion", value=maquina.state_machine_arn)
        cdk.CfnOutput(self, "ArnAgente", value=agente.function_arn)
        # What the gateway stack (activity 7) needs: its target and its inbound authorizer.
        self.herramientas, self.id_usuarios, self.id_cliente = herramientas, pool.ref, cliente.ref


def entorno_del_camino() -> dict:
    """The agent's tools path (activity 7), chosen at synth time: CAMINO_HERRAMIENTAS=directo (default) | gateway.
    The gateway's URL comes from the deployed semana19-gateway stack (S19_GATEWAY_URL, its output UrlGateway): the
    gateway depends on the tools function of this stack, so a reference the other way would be a cycle."""
    via = os.environ.get("CAMINO_HERRAMIENTAS") or "directo"
    if via not in ("directo", "gateway"):
        raise RuntimeError(f"CAMINO_HERRAMIENTAS desconocido: {via}")
    if via == "directo":
        return {"CAMINO_HERRAMIENTAS": "directo"}
    url = os.environ.get("S19_GATEWAY_URL", "")
    if not url.startswith("https://") or not url.endswith("/mcp"):
        raise RuntimeError("CAMINO_HERRAMIENTAS=gateway necesita S19_GATEWAY_URL (salida UrlGateway de semana19-gateway)")
    return {"CAMINO_HERRAMIENTAS": "gateway", "GATEWAY_URL": url}


NOMBRE_GATEWAY = "semana19-gateway"


def _esquema_cfn(e: dict):
    """A projected JSON schema (gateway/herramientas.json) as the target's SchemaDefinitionProperty."""
    return agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
        type=e["type"], description=e.get("description"), required=e.get("required"),
        items=_esquema_cfn(e["items"]) if "items" in e else None,
        properties={n: _esquema_cfn(p) for n, p in e["properties"].items()} if "properties" in e else None)


class Gateway(Stack):
    """Activity 7: the AgentCore Gateway (MCP) in front of the SAME tools function, with its Cedar policy engine in
    ENFORCE mode. Its own stack, deployed and destroyed apart from computo.

    Inbound: CUSTOM_JWT with the pool's discovery URL, the app client (Cognito access tokens carry client_id, not aud)
    and the scope legado/leer. Outbound: GATEWAY_IAM_ROLE, the only option for a Lambda target; the role may invoke
    the tools function and nothing else, evaluate this engine's policies and use the base key through AgentCore.
    The gateway and the engine are encrypted with the base key. No search (no Search-API or Tool-Indexing charges).
    """

    def __init__(self, scope: Construct, id: str, *, llave: kms.IKey, herramientas: lambda_.IFunction,
                 id_usuarios: str, id_cliente: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from gateway import esquemas, politicas
        from herramientas import contrato

        motor = agentcore.CfnPolicyEngine(
            self, "MotorDePoliticas", name="semana19_politicas", encryption_key_arn=llave.key_arn,
            description="Week 19, activity 7: the gateway's Cedar policies (gateway/politicas/*.cedar).")
        rol = iam.Role(
            self, "RolGateway", description="Execution role of semana19-gateway: invokes the tools function only.",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com", conditions={
                "StringEquals": {"aws:SourceAccount": Aws.ACCOUNT_ID},
                "ArnLike": {"aws:SourceArn": f"arn:{Aws.PARTITION}:bedrock-agentcore:{REGION}:{Aws.ACCOUNT_ID}:gateway/{NOMBRE_GATEWAY}-*"}}))
        rol.add_to_policy(_declaracion(sid="InvocarSoloHerramientas", actions=["lambda:InvokeFunction"],
                                       resources=[herramientas.function_arn]))
        rol.add_to_policy(_declaracion(sid="LeerSuMotorDePoliticas", actions=["bedrock-agentcore:GetPolicyEngine"],
                                       resources=[motor.attr_policy_engine_arn]))
        rol.add_to_policy(_declaracion(
            sid="LlaveBaseViaAgentCore", actions=["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey", "kms:CreateGrant"],
            resources=[llave.key_arn],
            conditions={"StringEquals": {"kms:ViaService": f"bedrock-agentcore.{REGION}.amazonaws.com"}}))

        gateway = agentcore.CfnGateway(
            self, "Gateway", name=NOMBRE_GATEWAY, protocol_type="MCP", role_arn=rol.role_arn,
            authorizer_type="CUSTOM_JWT", kms_key_arn=llave.key_arn,
            description="Week 19, activity 7: MCP gateway to the tools function, Cedar policies in ENFORCE.",
            authorizer_configuration=agentcore.CfnGateway.AuthorizerConfigurationProperty(
                custom_jwt_authorizer=agentcore.CfnGateway.CustomJWTAuthorizerConfigurationProperty(
                    discovery_url=f"https://cognito-idp.{REGION}.amazonaws.com/{id_usuarios}/.well-known/openid-configuration",
                    allowed_clients=[id_cliente], allowed_scopes=["legado/leer"])),
            policy_engine_configuration=agentcore.CfnGateway.GatewayPolicyEngineConfigurationProperty(
                arn=motor.attr_policy_engine_arn, mode="ENFORCE"))
        gateway.node.add_dependency(rol)
        # Policy evaluation needs both the engine and the gateway (policy-permissions.html): attached after the gateway.
        evaluar = iam.Policy(self, "EvaluarPoliticas", roles=[rol], statements=[_declaracion(
            sid="EvaluarSusPoliticas",
            actions=["bedrock-agentcore:AuthorizeAction", "bedrock-agentcore:PartiallyAuthorizeActions"],
            resources=[motor.attr_policy_engine_arn, gateway.attr_gateway_arn])])

        objetivo = agentcore.CfnGatewayTarget(
            self, "Herramientas", name=contrato.TARGET, gateway_identifier=gateway.attr_gateway_identifier,
            description="The tools function (describir_esquema, ejecutar_sql, proponer_orden_compra), its gateway adapter.",
            credential_provider_configurations=[agentcore.CfnGatewayTarget.CredentialProviderConfigurationProperty(
                credential_provider_type="GATEWAY_IAM_ROLE")],
            target_configuration=agentcore.CfnGatewayTarget.TargetConfigurationProperty(
                mcp=agentcore.CfnGatewayTarget.McpTargetConfigurationProperty(
                    lambda_=agentcore.CfnGatewayTarget.McpLambdaTargetConfigurationProperty(
                        lambda_arn=herramientas.function_arn,
                        tool_schema=agentcore.CfnGatewayTarget.ToolSchemaProperty(inline_payload=[
                            agentcore.CfnGatewayTarget.ToolDefinitionProperty(
                                name=d["name"], description=d["description"], input_schema=_esquema_cfn(d["inputSchema"]))
                            for d in esquemas.leer()])))))
        objetivo.node.add_dependency(evaluar)
        for nombre, texto in politicas.politicas().items():
            politica = agentcore.CfnPolicy(
                self, f"Politica{nombre.capitalize()}", name=nombre, policy_engine_id=motor.attr_policy_engine_id,
                validation_mode="FAIL_ON_ANY_FINDINGS", description=f"gateway/politicas/{nombre}.cedar",
                definition=agentcore.CfnPolicy.PolicyDefinitionProperty(cedar=agentcore.CfnPolicy.CedarPolicyProperty(
                    statement=politicas.con_gateway(texto, gateway.attr_gateway_arn))))
            politica.node.add_dependency(objetivo)   # validation checks the actions against the target's tools
        cdk.CfnOutput(self, "UrlGateway", value=gateway.attr_gateway_url)
        cdk.CfnOutput(self, "IdGateway", value=gateway.attr_gateway_identifier)


NOMBRE_AGENTE_COMPARACION = "semana19-agentes-comparacion"


def funciones_del_agente() -> list[dict]:
    """The action group's function details from the one schema source (gateway/herramientas.json), without the
    proposal's requester: on this path it comes from the session attributes the caller sets, never from the model."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from gateway import esquemas
    from herramientas import contrato
    salida = []
    for d in esquemas.leer():
        props = {n: e for n, e in d["inputSchema"].get("properties", {}).items() if n != contrato.SOLICITANTE}
        requeridos = set(d["inputSchema"].get("required", []))
        salida.append({"name": d["name"], "description": d["description"], "parameters": {
            n: {"type": e["type"], "description": e.get("description") or n, "required": n in requeridos}
            for n, e in props.items()}})
    return salida


def instruccion_del_agente(idioma: str = "es") -> str:
    """The system prompt of the pinned Prompt Management version (the same text semana19-ia publishes), rendered."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ia.config import NOMBRE_EMPRESA
    from ia.peticion import renderizar
    return renderizar(_cargar_hoja("prompts_sistema.py").PROMPTS[idioma], {"nombre_empresa": NOMBRE_EMPRESA[idioma]})


class AgentesComparacion(Stack):
    """Activity 7, path (c): a Bedrock Agent over the SAME tools function, for the comparison only. Disposable:
    deployed for the run and destroyed first.

    The instruction is the Spanish system prompt of its pinned version; the guardrail is semana19-ia's at its fixed
    version; the model is config.MODELO_ID. One action group, executor = the tools function (its Bedrock Agents
    adapter). The role (with the boundary) may use the model, the guardrail and the base key through Bedrock; the
    function is reached through its resource policy, for this agent only. Prepared by CloudFormation (AutoPrepare)
    and published as an alias.
    """

    def __init__(self, scope: Construct, id: str, *, llave: kms.IKey, herramientas: lambda_.IFunction,
                 guardrail_id: str, guardrail_version: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from herramientas import contrato
        from ia.config import MODELO_ID

        arn_agentes = f"arn:{Aws.PARTITION}:bedrock:{REGION}:{Aws.ACCOUNT_ID}:agent/*"
        rol = iam.Role(
            self, "RolAgente", description="Service role of the comparison agent: model, guardrail and key only.",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com", conditions={
                "StringEquals": {"aws:SourceAccount": Aws.ACCOUNT_ID}, "ArnLike": {"aws:SourceArn": arn_agentes}}))
        rol.add_to_policy(_declaracion(
            sid="ModeloDelAgente", actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream",
                                            "bedrock:GetInferenceProfile", "bedrock:GetFoundationModel"],
            resources=arns_modelo_del_agente()))
        rol.add_to_policy(_declaracion(
            sid="GuardrailDelAgente", actions=["bedrock:ApplyGuardrail"],
            resources=[f"arn:{Aws.PARTITION}:bedrock:{REGION}:{Aws.ACCOUNT_ID}:guardrail/{guardrail_id}",
                       *arns_perfil_guardrail()]))
        rol.add_to_policy(_declaracion(
            sid="LlaveBaseViaBedrock", actions=["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
            resources=[llave.key_arn], conditions={"StringEquals": {"kms:ViaService": f"bedrock.{REGION}.amazonaws.com"}}))

        agente = bedrock.CfnAgent(
            self, "Agente", agent_name=NOMBRE_AGENTE_COMPARACION, agent_resource_role_arn=rol.role_arn,
            foundation_model=MODELO_ID, instruction=instruccion_del_agente("es"), auto_prepare=True,
            customer_encryption_key_arn=llave.key_arn, idle_session_ttl_in_seconds=600,
            skip_resource_in_use_check_on_delete=True,
            description="Week 19, activity 7: path (c) of the tools comparison, disposable.",
            guardrail_configuration=bedrock.CfnAgent.GuardrailConfigurationProperty(
                guardrail_identifier=guardrail_id, guardrail_version=guardrail_version),
            action_groups=[bedrock.CfnAgent.AgentActionGroupProperty(
                action_group_name=contrato.TARGET, action_group_state="ENABLED",
                description="The tools function (describir_esquema, ejecutar_sql, proponer_orden_compra).",
                action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(lambda_=herramientas.function_arn),
                function_schema=bedrock.CfnAgent.FunctionSchemaProperty(functions=[
                    bedrock.CfnAgent.FunctionProperty(
                        name=f["name"], description=f["description"], require_confirmation="DISABLED",
                        parameters={n: bedrock.CfnAgent.ParameterDetailProperty(**p) for n, p in f["parameters"].items()})
                    for f in funciones_del_agente()]))])
        agente.node.add_dependency(rol)
        # The function's resource policy for this agent only (Bedrock invokes the executor as the service).
        permiso = lambda_.CfnPermission(
            self, "AgenteInvocaHerramientas", action="lambda:InvokeFunction", function_name=herramientas.function_arn,
            principal="bedrock.amazonaws.com", source_account=Aws.ACCOUNT_ID, source_arn=agente.attr_agent_arn)
        alias = bedrock.CfnAgentAlias(self, "Alias", agent_id=agente.attr_agent_id, agent_alias_name="comparacion",
                                      description="The prepared agent, as invoked by agentes/comparar.py.")
        alias.node.add_dependency(permiso)
        cdk.CfnOutput(self, "IdAgente", value=agente.attr_agent_id)
        cdk.CfnOutput(self, "IdAlias", value=alias.attr_agent_alias_id)


def construir(app: cdk.App) -> None:
    control = Control(app, "semana19-control", env=cdk.Environment(region=REGION))
    base = Base(app, "semana19-base", env=cdk.Environment(region=REGION),
                synthesizer=cdk.DefaultStackSynthesizer(qualifier="s19"))
    datos = Datos(app, "semana19-datos", red=base.red, llave=base.llave, env=cdk.Environment(region=REGION),
                  synthesizer=cdk.DefaultStackSynthesizer(qualifier="s19"))
    ia = Ia(app, "semana19-ia", llave=base.llave, env=cdk.Environment(region=REGION),
            synthesizer=cdk.DefaultStackSynthesizer(qualifier="s19"))
    pilas = [control, base, datos, ia]
    if os.environ.get("COMPUTO") == "1":
        computo = Computo(app, "semana19-computo", llave=base.llave, red=base.red, bd=datos.bd, sg_bd=datos.sg_bd,
                          sg_endpoints=base.sg_endpoints, guardrail_id=ia.guardrail_id,
                          guardrail_version=ia.guardrail_version, env=cdk.Environment(region=REGION),
                          synthesizer=cdk.DefaultStackSynthesizer(qualifier="s19"))
        gateway = Gateway(app, "semana19-gateway", llave=base.llave, herramientas=computo.herramientas,
                          id_usuarios=computo.id_usuarios, id_cliente=computo.id_cliente,
                          env=cdk.Environment(region=REGION), synthesizer=cdk.DefaultStackSynthesizer(qualifier="s19"))
        agentes = AgentesComparacion(app, NOMBRE_AGENTE_COMPARACION, llave=base.llave, herramientas=computo.herramientas,
                                     guardrail_id=ia.guardrail_id, guardrail_version=ia.guardrail_version,
                                     env=cdk.Environment(region=REGION),
                                     synthesizer=cdk.DefaultStackSynthesizer(qualifier="s19"))
        pilas += [computo, gateway, agentes]
    for pila in pilas:
        Aspects.of(pila).add(AplicarLimite())
        Aspects.of(pila).add(RetencionDeLogs())
        Aspects.of(pila).add(OmitirCheckovEnProveedorCdk())
        Aspects.of(pila).add(AwsSolutionsChecks(verbose=True))


if __name__ == "__main__":
    app = cdk.App()
    construir(app)
    app.synth()
