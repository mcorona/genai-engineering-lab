"""Week 19, activity 2: Guardrail, Knowledge Base and AgentCore Gateway in CDK, two ways. Synth only, $0."""
import aws_cdk as cdk
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_bedrockagentcore as agentcore
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3vectors as s3vectors
from aws_cdk import aws_bedrock_alpha as bedrock_alpha
from aws_cdk import aws_bedrock_agentcore_alpha as agentcore_alpha
from constructs import Construct

CUENTA = "000000000000"
TITAN_V2 = f"arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
JWT = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_EJEMPLO/.well-known/openid-configuration"


class IaL1(cdk.Stack):
    """Stable L1 constructs (aws-cdk-lib 2.276.0)."""

    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)
        llave = kms.Key(self, "Llave", enable_key_rotation=True, removal_policy=cdk.RemovalPolicy.DESTROY)
        bucket_vectores = s3vectors.CfnVectorBucket(
            self, "Vectores", vector_bucket_name=f"semana19-spike-vectores-{CUENTA}",
            encryption_configuration=s3vectors.CfnVectorBucket.EncryptionConfigurationProperty(
                sse_type="aws:kms", kms_key_arn=llave.key_arn))
        indice = s3vectors.CfnIndex(
            self, "Indice", vector_bucket_arn=bucket_vectores.attr_vector_bucket_arn,
            index_name="diccionario", data_type="float32", dimension=1024, distance_metric="cosine")
        rol_kb = iam.Role(self, "RolKb", assumed_by=iam.ServicePrincipal(
            "bedrock.amazonaws.com", conditions={"StringEquals": {"aws:SourceAccount": CUENTA}}))
        rol_kb.add_to_principal_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"], resources=[TITAN_V2]))
        rol_kb.add_to_principal_policy(iam.PolicyStatement(
            actions=["s3vectors:GetIndex", "s3vectors:QueryVectors", "s3vectors:PutVectors",
                     "s3vectors:GetVectors", "s3vectors:DeleteVectors"],
            resources=[indice.attr_index_arn]))
        bedrock.CfnKnowledgeBase(
            self, "Kb", name="semana19-spike-diccionario", role_arn=rol_kb.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=TITAN_V2,
                    embedding_model_configuration=bedrock.CfnKnowledgeBase.EmbeddingModelConfigurationProperty(
                        bedrock_embedding_model_configuration=bedrock.CfnKnowledgeBase.BedrockEmbeddingModelConfigurationProperty(
                            dimensions=1024, embedding_data_type="FLOAT32")))),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="S3_VECTORS",
                s3_vectors_configuration=bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                    index_arn=indice.attr_index_arn)))
        rol_gw = iam.Role(self, "RolGateway", assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"))
        agentcore.CfnGateway(
            self, "Gateway", name="semana19-spike-gateway", role_arn=rol_gw.role_arn,
            authorizer_type="CUSTOM_JWT", protocol_type="MCP",
            authorizer_configuration=agentcore.CfnGateway.AuthorizerConfigurationProperty(
                custom_jwt_authorizer=agentcore.CfnGateway.CustomJWTAuthorizerConfigurationProperty(
                    discovery_url=JWT, allowed_audience=["semana19-agente"])))
        bedrock.CfnGuardrail(
            self, "Guardrail", name="semana19-spike-guardrail-l1",
            blocked_input_messaging="Bloqueado", blocked_outputs_messaging="Bloqueado")


class IaAlpha(cdk.Stack):
    """L2 alpha constructs (2.276.0a0)."""

    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)
        bedrock_alpha.Guardrail(self, "Guardrail", guardrail_name="semana19-spike-guardrail-l2",
                                blocked_input_messaging="Bloqueado", blocked_outputs_messaging="Bloqueado")
        # El L2 alpha de KB solo acepta VectorStore.open_search_serverless (no S3 Vectors): se mide, no se usa.
        agentcore_alpha.Gateway(self, "Gateway", gateway_name="semana19-spike-gateway-l2",
                                authorizer_configuration=agentcore_alpha.GatewayAuthorizer.using_custom_jwt(
                                    discovery_url=JWT, allowed_audience=["semana19-agente"]))


app = cdk.App()
env = cdk.Environment(account=CUENTA, region="us-east-1")
IaL1(app, "semana19-ia-l1", env=env)
IaAlpha(app, "semana19-ia-alpha", env=env)
app.synth()
