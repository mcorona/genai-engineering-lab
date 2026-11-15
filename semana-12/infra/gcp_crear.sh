#!/usr/bin/env bash
# Week 12, activity 1 (Google Cloud): a budget with alerts and a least-privilege service account that is used through
# impersonation (no key files). Idempotent. The project owner runs it. It creates no billable resources.
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
P=$GCP_PROYECTO
YO=$(gcloud config get-value account 2>/dev/null)
echo "project $P, as $YO"
gcloud services enable billingbudgets.googleapis.com iamcredentials.googleapis.com iam.googleapis.com --project=$P

# 1. A budget limited to the project, with alerts at 50, 90 and 100 % (email to the billing administrators).
CTA=$(gcloud billing projects describe $P --format='value(billingAccountName.basename())')
if gcloud billing budgets list --billing-account=$CTA --format='value(displayName)' | grep -qx "$PREFIJO"; then
  echo "budget $PREFIJO: already exists"
else
  # The amount is in the billing account's currency (a Mexican account bills in MXN).
  MONEDA=$(gcloud billing accounts describe $CTA --format='value(currencyCode)')
  if [ "$MONEDA" = "USD" ]; then MONTO=$PRESUPUESTO_USD; else MONTO=${PRESUPUESTO_GCP_LOCAL:?Define PRESUPUESTO_GCP_LOCAL con el equivalente a $PRESUPUESTO_USD USD en $MONEDA}; fi
  echo "billing account currency: $MONEDA; budget: $MONTO $MONEDA"
  gcloud billing budgets create --billing-account=$CTA --display-name="$PREFIJO" --budget-amount=${MONTO}${MONEDA} \
    --filter-projects=projects/$P --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0 \
    --threshold-rule=percent=1.0,basis=forecasted-spend >/dev/null
  echo "budget $PREFIJO: created ($MONTO $MONEDA, only the project $P)"
fi

# 2. The operator service account: Discovery Engine (create and query data stores and apps) and nothing else at the project level.
#    Access to the document bucket is granted on the bucket itself when it is created (activity 2), not at the project level.
if ! gcloud iam service-accounts describe $GCP_SA_EMAIL --project=$P >/dev/null 2>&1; then
  gcloud iam service-accounts create $GCP_SA --project=$P --display-name="Semana 12: operador de Vertex AI Search"
fi
gcloud projects add-iam-policy-binding $P --member=serviceAccount:$GCP_SA_EMAIL --role=roles/discoveryengine.editor --condition=None >/dev/null
# Using the project as the quota project (x-goog-user-project) requires serviceusage.services.use.
gcloud projects add-iam-policy-binding $P --member=serviceAccount:$GCP_SA_EMAIL --role=roles/serviceusage.serviceUsageConsumer --condition=None >/dev/null
# 3. Only your user can generate tokens for the service account (impersonation); no keys are created.
gcloud iam service-accounts add-iam-policy-binding $GCP_SA_EMAIL --project=$P \
  --member=user:$YO --role=roles/iam.serviceAccountTokenCreator >/dev/null
N=$(gcloud iam service-accounts keys list --iam-account=$GCP_SA_EMAIL --managed-by=user --format='value(name)' | wc -l | tr -d ' ')
echo "service account $GCP_SA_EMAIL: roles/discoveryengine.editor and serviceusage.serviceUsageConsumer; user-managed keys: $N (must be 0)"
sleep 20  # IAM propagation
gcloud auth print-access-token --impersonate-service-account=$GCP_SA_EMAIL >/dev/null 2>&1 \
  && echo "impersonation: OK" || echo "impersonation: not propagated yet; retry in 1 minute"
echo "Google Cloud ready. For the week: gcloud auth application-default login --impersonate-service-account=$GCP_SA_EMAIL"
