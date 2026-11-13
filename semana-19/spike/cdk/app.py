"""Week 19, activity 2: minimal IaC spike (CDK, Python). Same stack as spike/terraform. Synth only, $0."""
import aws_cdk as cdk
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from cdk_nag import AwsSolutionsChecks
from constructs import Construct


class SpikeStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)
        llave = kms.Key(self, "Llave", enable_key_rotation=True, removal_policy=cdk.RemovalPolicy.DESTROY)
        registros = s3.Bucket(
            self, "Registros", encryption=s3.BucketEncryption.KMS, encryption_key=llave,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True,
            removal_policy=cdk.RemovalPolicy.DESTROY, auto_delete_objects=False, versioned=True)
        registros.node.default_child.cfn_options.metadata = {"checkov": {"skip": [{
            "id": "CKV_AWS_18",
            "comment": "Bucket de destino de los logs de acceso: AWS no permite que un bucket se registre a sí mismo."}]}}
        bucket = s3.Bucket(
            self, "Datos", encryption=s3.BucketEncryption.KMS, encryption_key=llave,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True,
            removal_policy=cdk.RemovalPolicy.DESTROY, auto_delete_objects=False,
            versioned=True, server_access_logs_bucket=registros,
            server_access_logs_prefix="datos/")
        frontera = iam.ManagedPolicy(
            self, "Frontera", statements=[iam.PolicyStatement(
                actions=["s3:GetObject", "s3:PutObject"], resources=[bucket.arn_for_objects("*")])])
        rol = iam.Role(
            self, "Rol", assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            permissions_boundary=frontera)
        bucket.grant_read(rol)
        guardrail = bedrock.CfnGuardrail(
            self, "Guardrail", name="semana19-spike-guardrail",
            blocked_input_messaging="Bloqueado", blocked_outputs_messaging="Bloqueado",
            kms_key_arn=llave.key_arn,
            content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
                filters_config=[bedrock.CfnGuardrail.ContentFilterConfigProperty(
                    input_strength="HIGH", output_strength="HIGH", type="PROMPT_ATTACK")]))
        cdk.Tags.of(self).add("proyecto", "semana19")
        cdk.CfnOutput(self, "GuardrailId", value=guardrail.attr_guardrail_id)


app = cdk.App()
stack = SpikeStack(app, "semana19-spike", env=cdk.Environment(account="000000000000", region="us-east-1"))
AwsSolutionsChecks(stack, verbose=True)
app.synth()
