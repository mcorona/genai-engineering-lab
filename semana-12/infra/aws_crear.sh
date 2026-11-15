#!/usr/bin/env bash
# Week 12, activity 1 (AWS): a budget with alerts, the Knowledge Base service role and an operator role with
# least privilege, plus the `semana12` profile that assumes that role. Idempotent. An administrator runs it (manuel-admin).
# It creates no billable resources (buckets, vector buckets, KBs): those come in activities 2 and 4.
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
export AWS_PAGER=""
[ -n "$CUENTA_AWS" ] || { echo "No AWS session (aws login)"; exit 1; }
[ -n "$ALERTA_CORREO" ] || { echo "Set ALERTA_CORREO=<email> for the budget alerts"; exit 1; }
YO=$(aws sts get-caller-identity --query Arn --output text)
echo "account $CUENTA_AWS, region $REGION, as $YO"
TMP=$(mktemp -d)

# 1. The account's monthly budget (costs by tag require activating the cost allocation tag and take 24 h).
if aws budgets describe-budget --account-id "$CUENTA_AWS" --budget-name "$PREFIJO" >/dev/null 2>&1; then
  echo "budget $PREFIJO: already exists"
else
  cat > $TMP/presupuesto.json <<J
{"BudgetName":"$PREFIJO","BudgetLimit":{"Amount":"$PRESUPUESTO_USD","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST"}
J
  python3 - "$ALERTA_CORREO" > $TMP/avisos.json <<'P'
import json, sys
s = [{"SubscriptionType": "EMAIL", "Address": sys.argv[1]}]
n = [{"Notification": {"NotificationType": t, "ComparisonOperator": "GREATER_THAN", "Threshold": u, "ThresholdType": "PERCENTAGE"}, "Subscribers": s}
     for t, u in (("ACTUAL", 50), ("ACTUAL", 90), ("ACTUAL", 100), ("FORECASTED", 100))]
print(json.dumps(n))
P
  aws budgets create-budget --account-id "$CUENTA_AWS" --budget file://$TMP/presupuesto.json \
    --notifications-with-subscribers file://$TMP/avisos.json
  echo "budget $PREFIJO: created (\$$PRESUPUESTO_USD per month; alerts at 50/90/100 % actual and 100 % forecasted)"
fi

etiquetas="Key=$ETIQUETA_CLAVE,Value=$ETIQUETA_VALOR"
crear_rol() {  # name, trust policy file
  if aws iam get-role --role-name "$1" >/dev/null 2>&1; then
    aws iam update-assume-role-policy --role-name "$1" --policy-document file://$2; echo "role $1: trust policy updated"
  else
    aws iam create-role --role-name "$1" --assume-role-policy-document file://$2 --tags $etiquetas --max-session-duration 14400 >/dev/null
    echo "role $1: created"
  fi
}
lista() { local p=$1; shift; local out=""; for x in "$@"; do out+="\"${p}${x}\","; done; echo "${out%,}"; }

# 2. The Knowledge Base service role: reads the document bucket, writes to and queries the vector bucket, embeds.
cat > $TMP/confianza_kb.json <<J
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"bedrock.amazonaws.com"},"Action":"sts:AssumeRole",
 "Condition":{"StringEquals":{"aws:SourceAccount":"$CUENTA_AWS"},"ArnLike":{"aws:SourceArn":"arn:aws:bedrock:$REGION:$CUENTA_AWS:knowledge-base/*"}}}]}
J
cat > $TMP/permisos_kb.json <<J
{"Version":"2012-10-17","Statement":[
 {"Sid":"LeerDocumentos","Effect":"Allow","Action":["s3:GetObject","s3:ListBucket"],"Resource":["arn:aws:s3:::$S3_DOCS","arn:aws:s3:::$S3_DOCS/*"],
  "Condition":{"StringEquals":{"aws:ResourceAccount":"$CUENTA_AWS"}}},
 {"Sid":"VectorBucket","Effect":"Allow","Action":["s3vectors:PutVectors","s3vectors:GetVectors","s3vectors:DeleteVectors","s3vectors:QueryVectors","s3vectors:ListVectors","s3vectors:GetIndex"],
  "Resource":["arn:aws:s3vectors:$REGION:$CUENTA_AWS:bucket/$S3_VECTORES","arn:aws:s3vectors:$REGION:$CUENTA_AWS:bucket/$S3_VECTORES/index/*"]},
 {"Sid":"Embeddings","Effect":"Allow","Action":["bedrock:InvokeModel"],"Resource":[$(lista "arn:aws:bedrock:$REGION::foundation-model/" "${MODELOS_EMB[@]}")]},
 {"Sid":"AlmacenamientoMultimodal","Effect":"Allow","Action":["s3:PutObject","s3:GetObject","s3:DeleteObject","s3:ListBucket"],
  "Resource":["arn:aws:s3:::$S3_MULTIMODAL","arn:aws:s3:::$S3_MULTIMODAL/*"],"Condition":{"StringEquals":{"aws:ResourceAccount":"$CUENTA_AWS"}}},
 {"Sid":"ParserBDA","Effect":"Allow","Action":["bedrock:InvokeDataAutomationAsync"],"Resource":[
   "arn:aws:bedrock:$REGION:aws:data-automation-project/public-rag-default","arn:aws:bedrock:us-*:$CUENTA_AWS:data-automation-profile/*"]},
 {"Sid":"ParserBDAEstado","Effect":"Allow","Action":["bedrock:GetDataAutomationStatus"],"Resource":"arn:aws:bedrock:us-*:$CUENTA_AWS:data-automation-invocation/*"}]}
J
crear_rol "$ROL_KB" $TMP/confianza_kb.json
aws iam put-role-policy --role-name "$ROL_KB" --policy-name "${PREFIJO}-kb" --policy-document file://$TMP/permisos_kb.json

# 3. The operator role: assumed by the user who runs the week; only resources with the semana12 prefix and the models used.
cat > $TMP/confianza_op.json <<J
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"AWS":"$YO"},"Action":"sts:AssumeRole"}]}
J
cat > $TMP/permisos_op.json <<J
{"Version":"2012-10-17","Statement":[
 {"Sid":"Lectura","Effect":"Allow","Action":["bedrock:ListFoundationModels","bedrock:GetFoundationModel","bedrock:ListInferenceProfiles","bedrock:GetInferenceProfile",
   "bedrock:ListKnowledgeBases","s3:ListAllMyBuckets","s3vectors:ListVectorBuckets","budgets:ViewBudget"],"Resource":"*"},
 {"Sid":"CrearKnowledgeBase","Effect":"Allow","Action":["bedrock:CreateKnowledgeBase"],"Resource":"*",
  "Condition":{"StringEquals":{"aws:RequestTag/$ETIQUETA_CLAVE":"$ETIQUETA_VALOR"}}},
 {"Sid":"KnowledgeBases","Effect":"Allow","Action":["bedrock:GetKnowledgeBase","bedrock:UpdateKnowledgeBase","bedrock:DeleteKnowledgeBase",
   "bedrock:CreateDataSource","bedrock:GetDataSource","bedrock:UpdateDataSource","bedrock:DeleteDataSource","bedrock:ListDataSources",
   "bedrock:StartIngestionJob","bedrock:GetIngestionJob","bedrock:ListIngestionJobs","bedrock:Retrieve","bedrock:TagResource","bedrock:ListTagsForResource"],
  "Resource":"arn:aws:bedrock:$REGION:$CUENTA_AWS:knowledge-base/*"},
 {"Sid":"RetrieveAndGenerate","Effect":"Allow","Action":["bedrock:RetrieveAndGenerate"],"Resource":"*"},
 {"Sid":"Modelos","Effect":"Allow","Action":["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream"],"Resource":[
   $(lista "arn:aws:bedrock:$REGION::foundation-model/" "${MODELOS_EMB[@]}"),
   $(lista "arn:aws:bedrock:$REGION:$CUENTA_AWS:inference-profile/" "${PERFILES_CLAUDE[@]}"),
   $(lista "arn:aws:bedrock:us-*::foundation-model/" "${MODELOS_CLAUDE[@]}")]},
 {"Sid":"Buckets","Effect":"Allow","Action":["s3:CreateBucket","s3:DeleteBucket","s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject",
   "s3:PutBucketTagging","s3:GetBucketTagging","s3:PutBucketPublicAccessBlock","s3:PutEncryptionConfiguration"],
  "Resource":["arn:aws:s3:::$S3_DOCS","arn:aws:s3:::$S3_DOCS/*","arn:aws:s3:::$S3_MULTIMODAL","arn:aws:s3:::$S3_MULTIMODAL/*"]},
 {"Sid":"VectorBucket","Effect":"Allow","Action":"s3vectors:*",
  "Resource":["arn:aws:s3vectors:$REGION:$CUENTA_AWS:bucket/$S3_VECTORES","arn:aws:s3vectors:$REGION:$CUENTA_AWS:bucket/$S3_VECTORES/index/*"]},
 {"Sid":"PasarRolKB","Effect":"Allow","Action":"iam:PassRole","Resource":"arn:aws:iam::$CUENTA_AWS:role/$ROL_KB",
  "Condition":{"StringEquals":{"iam:PassedToService":"bedrock.amazonaws.com"}}}]}
J
crear_rol "$ROL_OPERADOR" $TMP/confianza_op.json
aws iam put-role-policy --role-name "$ROL_OPERADOR" --policy-name "${PREFIJO}-operador" --policy-document file://$TMP/permisos_op.json

# 4. The local `semana12` profile (in ~/.aws/config, outside the repository) that assumes the operator role with the current session.
aws configure set profile.$PERFIL_AWS.role_arn "arn:aws:iam::$CUENTA_AWS:role/$ROL_OPERADOR"
aws configure set profile.$PERFIL_AWS.source_profile "${AWS_PROFILE:-default}"
aws configure set profile.$PERFIL_AWS.region "$REGION"
sleep 10  # IAM propagation
aws sts get-caller-identity --profile $PERFIL_AWS --query Arn --output text | sed 's/^/perfil semana12 asume: /'
rm -rf $TMP
echo "AWS ready. Use --profile $PERFIL_AWS (or AWS_PROFILE=$PERFIL_AWS) in the week's scripts."
