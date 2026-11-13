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
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
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
DESPLIEGUE = "semana19-despliegue"
ROL_PRESUPUESTO = "semana19-accion-presupuesto"
OPERADOR = "manuel-admin"
PRESUPUESTO = "semana19"
PRESUPUESTO_USD = 5.0
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
            resources=[ARN_LIMITE, ARN_CONGELAR, ARN_EJECUCION_CFN]))
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
        saltar_checkov(ejecucion, {
            "CKV_AWS_111": "Creación de recursos del proyecto sin ARN previo (VPC, llaves, grupos); ver EXCEPCIONES.",
            "CKV_AWS_109": "Gestión de roles limitada a nombres semana19-* y obligatoriamente con el límite (condición iam:PermissionsBoundary); ver EXCEPCIONES."})
        suprimir_iam5(despliegue, ["AsumirRolesCdk", "LeerCloudFormation", "CrearRolesSoloConLimite",
                                   "NoQuitarNiCambiarElLimite"])
        cdk.CfnOutput(self, "ArnLimite", value=limite.managed_policy_arn)
        cdk.CfnOutput(self, "ArnDespliegue", value=despliegue.role_arn)
        cdk.CfnOutput(self, "ArnCongelar", value=congelar.managed_policy_arn)
        cdk.CfnOutput(self, "ArnEjecucionCfn", value=ejecucion.managed_policy_arn)


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
    for pila in (control, base):
        Aspects.of(pila).add(AplicarLimite())
        Aspects.of(pila).add(RetencionDeLogs())
        Aspects.of(pila).add(OmitirCheckovEnProveedorCdk())
        Aspects.of(pila).add(AwsSolutionsChecks(verbose=True))


if __name__ == "__main__":
    app = cdk.App()
    construir(app)
    app.synth()
