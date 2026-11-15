#!/usr/bin/env bash
# Week 12, activity 9 (AWS, run by the administrator): the semana12-ci role, which only a GitHub Actions job of this
# repository's nube-semana12 environment can assume, through GitHub OIDC. No access keys. Query-only permissions: Retrieve,
# RetrieveAndGenerate and invoking the models they use (Haiku and embeddings). It cannot create or delete anything.
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
export AWS_PAGER=""
SUJETO=$(gh_sujeto)
TMP=$(mktemp -d)
PROV=$(aws iam list-open-id-connect-providers --query "OpenIDConnectProviderList[?contains(Arn,'token.actions.githubusercontent.com')].Arn" --output text)
if [ -z "$PROV" ]; then
  PROV=$(aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com --client-id-list sts.amazonaws.com \
    --tags Key=$ETIQUETA_CLAVE,Value=$ETIQUETA_VALOR --query OpenIDConnectProviderArn --output text)
  echo "GitHub OIDC provider: created ($PROV)"
else
  echo "GitHub OIDC provider: already existed ($PROV); activity 10 does not delete it if week 12 did not create it"
fi
cat > $TMP/confianza.json <<J
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Federated":"$PROV"},"Action":"sts:AssumeRoleWithWebIdentity",
 "Condition":{"StringEquals":{"token.actions.githubusercontent.com:aud":"sts.amazonaws.com",
   "token.actions.githubusercontent.com:sub":"$SUJETO"}}}]}
J
lista() { local p=$1; shift; local out=""; for x in "$@"; do out+="\"${p}${x}\","; done; echo "${out%,}"; }
cat > $TMP/permisos.json <<J
{"Version":"2012-10-17","Statement":[
 {"Sid":"Lectura","Effect":"Allow","Action":["bedrock:ListKnowledgeBases","bedrock:GetInferenceProfile"],"Resource":"*"},
 {"Sid":"Consultar","Effect":"Allow","Action":["bedrock:Retrieve","bedrock:GetKnowledgeBase"],"Resource":"arn:aws:bedrock:$REGION:$CUENTA_AWS:knowledge-base/*"},
 {"Sid":"RetrieveAndGenerate","Effect":"Allow","Action":["bedrock:RetrieveAndGenerate"],"Resource":"*"},
 {"Sid":"Modelos","Effect":"Allow","Action":["bedrock:InvokeModel"],"Resource":[
   $(lista "arn:aws:bedrock:$REGION::foundation-model/" "${MODELOS_EMB[@]}"),
   $(lista "arn:aws:bedrock:$REGION:$CUENTA_AWS:inference-profile/" "${PERFILES_CLAUDE[@]}"),
   $(lista "arn:aws:bedrock:us-*::foundation-model/" "${MODELOS_CLAUDE[@]}")]}]}
J
if aws iam get-role --role-name $ROL_CI >/dev/null 2>&1; then
  aws iam update-assume-role-policy --role-name $ROL_CI --policy-document file://$TMP/confianza.json
else
  aws iam create-role --role-name $ROL_CI --assume-role-policy-document file://$TMP/confianza.json \
    --tags Key=$ETIQUETA_CLAVE,Value=$ETIQUETA_VALOR --max-session-duration 3600 >/dev/null
fi
aws iam put-role-policy --role-name $ROL_CI --policy-name ${PREFIJO}-ci --policy-document file://$TMP/permisos.json
rm -rf $TMP
echo "role $ROL_CI: arn:aws:iam::$CUENTA_AWS:role/$ROL_CI (only $SUJETO)"
