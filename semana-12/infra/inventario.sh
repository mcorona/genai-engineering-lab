#!/usr/bin/env bash
# Week 12: lists the week's resources that still exist in each cloud (the ones that can bill). Read-only.
#   ./inventario.sh [aws|gcp|all]      (todo, the default, also means all)
set -uo pipefail
cd "$(dirname "$0")"; source config.sh
export AWS_PAGER=""
QUE=${1:-todo}; N=0
linea() { printf "  %-34s %s\n" "$1" "${2:-(none)}"; [ -n "${2:-}" ] && N=$((N+1)); return 0; }
if [ "$QUE" != gcp ]; then
  echo "AWS ($CUENTA_AWS, $REGION)"
  linea "Knowledge Bases semana12" "$(aws bedrock-agent list-knowledge-bases --region $REGION --query "knowledgeBaseSummaries[?starts_with(name,'$PREFIJO')].name" --output text 2>/dev/null)"
  linea "S3 vector buckets semana12" "$(aws s3vectors list-vector-buckets --region $REGION --query "vectorBuckets[?starts_with(vectorBucketName,'$PREFIJO')].vectorBucketName" --output text 2>/dev/null)"
  linea "Buckets S3 semana12" "$(aws s3api list-buckets --query "Buckets[?starts_with(Name,'$PREFIJO')].Name" --output text 2>/dev/null)"
  linea "Roles IAM semana12 (sin costo)" "$(aws iam list-roles --query "Roles[?starts_with(RoleName,'$PREFIJO')].RoleName" --output text 2>/dev/null)"
  linea "CI: proveedor OIDC (sin costo)" "$(aws iam list-open-id-connect-providers --query "OpenIDConnectProviderList[?contains(Arn,'token.actions.githubusercontent.com')].Arn" --output text 2>/dev/null | sed 's|.*/||')"
  linea "Presupuesto semana12 (sin costo)" "$(aws budgets describe-budgets --account-id "$CUENTA_AWS" --query "Budgets[?BudgetName=='$PREFIJO'].BudgetName" --output text 2>/dev/null)"
fi
if [ "$QUE" != aws ]; then
  P=$GCP_PROYECTO; TOKEN=$(gcloud auth print-access-token 2>/dev/null)
  API="https://discoveryengine.googleapis.com/v1/projects/$P/locations/$GCP_UBICACION/collections/default_collection"
  nombres() { curl -s -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $P" "$API/$1" | \
    python3 -c "import json,sys; d=json.load(sys.stdin); print(' '.join(x['name'].split('/')[-1] for x in d.get('$1',[])))" 2>/dev/null; }
  echo "Google Cloud ($P, $GCP_UBICACION)"
  linea "Data stores (all)" "$(nombres dataStores)"
  linea "Apps / engines (all)" "$(nombres engines)"
  linea "Buckets GCS semana12" "$(gcloud storage buckets list --project=$P --format='value(name)' 2>/dev/null | grep "^$PREFIJO" | tr '\n' ' ')"
  CTA=$(gcloud billing projects describe $P --format='value(billingAccountName.basename())' 2>/dev/null)
  linea "Presupuesto semana12 (sin costo)" "$(gcloud billing budgets list --billing-account=$CTA --filter="displayName=$PREFIJO" --format='value(displayName)' 2>/dev/null)"
  linea "CI: pool de identidad (sin costo)" "$(gcloud iam workload-identity-pools list --location=global --project=$P --filter="name~$GCP_POOL" --format='value(name.basename())' 2>/dev/null)"
  linea "Cuenta de servicio (sin costo)" "$(gcloud iam service-accounts list --project=$P --filter="email:$GCP_SA_EMAIL" --format='value(email)' 2>/dev/null)"
fi
echo "GitHub ($GH_REPO)"
linea "Entorno $GH_ENTORNO (secretos)" "$(gh api repos/$GH_REPO/environments --jq ".environments[]|select(.name==\"$GH_ENTORNO\")|.name" 2>/dev/null)"
echo "Week resources present: $N (the ones marked 'sin costo' do not bill)"
