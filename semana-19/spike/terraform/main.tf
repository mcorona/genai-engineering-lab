variable "cuenta" {
  description = "ID de cuenta para nombres de bucket; en el repo va como placeholder"
  type        = string
  default     = "000000000000"
}

resource "aws_kms_key" "llave" {
  description         = "semana19 spike"
  enable_key_rotation = true
  deletion_window_in_days = 7
}

resource "aws_s3_bucket" "registros" {
  #checkov:skip=CKV_AWS_144:Lab: el bucket de logs no se replica entre regiones; prod lo decide el ADR 0006.
  #checkov:skip=CKV2_AWS_62:Bucket de logs de acceso: no emite notificaciones de eventos.
  bucket        = "semana19-spike-registros-${var.cuenta}"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "registros" {
  bucket = aws_s3_bucket.registros.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "registros" {
  bucket = aws_s3_bucket.registros.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.llave.arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "registros" {
  bucket                  = aws_s3_bucket.registros.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "datos" {
  #checkov:skip=CKV_AWS_144:Lab: el bucket de datos no se replica entre regiones; prod lo decide el ADR 0006.
  #checkov:skip=CKV2_AWS_62:Lab: sin notificaciones de eventos en el spike.
  bucket        = "semana19-spike-datos-${var.cuenta}"
  force_destroy = false
}

resource "aws_s3_bucket_versioning" "datos" {
  bucket = aws_s3_bucket.datos.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "datos" {
  bucket = aws_s3_bucket.datos.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.llave.arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "datos" {
  bucket                  = aws_s3_bucket.datos.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_logging" "datos" {
  bucket        = aws_s3_bucket.datos.id
  target_bucket = aws_s3_bucket.registros.id
  target_prefix = "datos/"
}

data "aws_iam_policy_document" "tls" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.datos.arn, "${aws_s3_bucket.datos.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "datos" {
  bucket = aws_s3_bucket.datos.id
  policy = data.aws_iam_policy_document.tls.json
}

data "aws_iam_policy_document" "frontera" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.datos.arn}/*"]
  }
}

resource "aws_iam_policy" "frontera" {
  name   = "semana19-spike-frontera"
  policy = data.aws_iam_policy_document.frontera.json
}

data "aws_iam_policy_document" "asume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "rol" {
  name                 = "semana19-spike-rol"
  assume_role_policy   = data.aws_iam_policy_document.asume.json
  permissions_boundary = aws_iam_policy.frontera.arn
}

resource "aws_bedrock_guardrail" "guardrail" {
  name                      = "semana19-spike-guardrail"
  blocked_input_messaging   = "Bloqueado"
  blocked_outputs_messaging = "Bloqueado"
  kms_key_arn               = aws_kms_key.llave.arn
  content_policy_config {
    filters_config {
      input_strength  = "HIGH"
      output_strength = "HIGH"
      type            = "PROMPT_ATTACK"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "registros" {
  bucket = aws_s3_bucket.registros.id
  rule {
    id     = "expira-registros"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
    expiration {
      days = 90
    }
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "datos" {
  bucket = aws_s3_bucket.datos.id
  rule {
    id     = "versiones-antiguas"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

data "aws_iam_policy_document" "llave" {
  statement {
    sid       = "RaizDeLaCuenta"
    actions   = ["kms:Create*", "kms:Describe*", "kms:Enable*", "kms:List*", "kms:Put*", "kms:Update*", "kms:Revoke*", "kms:Disable*", "kms:Get*", "kms:Delete*", "kms:ScheduleKeyDeletion", "kms:CancelKeyDeletion", "kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey*", "kms:ReEncrypt*"]
    #checkov:skip=CKV_AWS_109:Política por omisión de KMS: el root de la cuenta debe poder administrar la llave, o la cuenta la pierde.
    #checkov:skip=CKV_AWS_111:Mismo motivo: la administración de la llave es la política por omisión de KMS, no un permiso amplio de escritura.
    #checkov:skip=CKV_AWS_356:En una política de llave KMS, "*" en resources significa esta llave; no es un comodín global.
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${var.cuenta}:root"]
    }
  }
}

resource "aws_kms_key_policy" "llave" {
  key_id = aws_kms_key.llave.id
  policy = data.aws_iam_policy_document.llave.json
}
