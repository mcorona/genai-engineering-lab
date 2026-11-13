# Knowledge Base (diccionario de datos) en S3 Vectors con Titan Text Embeddings V2, y AgentCore Gateway.
# Solo se valida y se planea: no se aplica nada en la cuenta.

locals {
  titan_v2_arn = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
}

resource "aws_s3vectors_vector_bucket" "vectores" {
  vector_bucket_name = "semana19-spike-vectores-${var.cuenta}"
  force_destroy      = true
  encryption_configuration {
    sse_type    = "aws:kms"
    kms_key_arn = aws_kms_key.llave.arn
  }
}

resource "aws_s3vectors_index" "diccionario" {
  vector_bucket_name = aws_s3vectors_vector_bucket.vectores.vector_bucket_name
  index_name         = "diccionario"
  data_type          = "float32"
  dimension          = 1024
  distance_metric    = "cosine"
  encryption_configuration {
    sse_type    = "aws:kms"
    kms_key_arn = aws_kms_key.llave.arn
  }
}

data "aws_iam_policy_document" "asume_kb" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.cuenta]
    }
  }
}

data "aws_iam_policy_document" "kb" {
  statement {
    actions   = ["bedrock:InvokeModel"]
    resources = [local.titan_v2_arn]
  }
  statement {
    actions   = ["s3vectors:GetIndex", "s3vectors:QueryVectors", "s3vectors:PutVectors", "s3vectors:GetVectors", "s3vectors:DeleteVectors"]
    resources = [aws_s3vectors_index.diccionario.index_arn]
  }
}

resource "aws_iam_role" "kb" {
  name               = "semana19-spike-kb"
  assume_role_policy = data.aws_iam_policy_document.asume_kb.json
}

resource "aws_iam_role_policy" "kb" {
  name   = "semana19-spike-kb"
  role   = aws_iam_role.kb.id
  policy = data.aws_iam_policy_document.kb.json
}

resource "aws_bedrockagent_knowledge_base" "diccionario" {
  name     = "semana19-spike-diccionario"
  role_arn = aws_iam_role.kb.arn
  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = local.titan_v2_arn
      embedding_model_configuration {
        bedrock_embedding_model_configuration {
          dimensions          = 1024
          embedding_data_type = "FLOAT32"
        }
      }
    }
  }
  storage_configuration {
    type = "S3_VECTORS"
    s3_vectors_configuration {
      index_arn = aws_s3vectors_index.diccionario.index_arn
    }
  }
  depends_on = [aws_iam_role_policy.kb]
}

data "aws_iam_policy_document" "asume_gw" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "gateway" {
  name               = "semana19-spike-gateway"
  assume_role_policy = data.aws_iam_policy_document.asume_gw.json
}

resource "aws_bedrockagentcore_gateway" "herramientas" {
  name            = "semana19-spike-gateway"
  role_arn        = aws_iam_role.gateway.arn
  authorizer_type = "CUSTOM_JWT"
  protocol_type   = "MCP"
  authorizer_configuration {
    custom_jwt_authorizer {
      discovery_url    = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_EJEMPLO/.well-known/openid-configuration"
      allowed_audience = ["semana19-agente"]
    }
  }
  protocol_configuration {
    mcp {}
  }
}
