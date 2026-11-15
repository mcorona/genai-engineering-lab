#!/usr/bin/env bash
# Week 12, activity 9 (Google Cloud, run by the owner): Workload Identity Federation for GitHub Actions, without keys.
# The semana12-github pool with a GitHub OIDC provider limited to this repository; the semana12-ci service account (Discovery Engine
# viewer: search and rank, without creating or deleting) that only the subject repo:<repo>:environment:nube-semana12 can use.
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
SUJETO=$(gh_sujeto); P=$GCP_PROYECTO; NUM=$(gcloud projects describe $P --format='value(projectNumber)')
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com --project=$P
gcloud iam service-accounts describe $GCP_SA_CI_EMAIL --project=$P >/dev/null 2>&1 || \
  gcloud iam service-accounts create $GCP_SA_CI --project=$P --display-name="Semana 12: CI manual (solo consulta)"
for r in roles/discoveryengine.viewer roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding $P --member=serviceAccount:$GCP_SA_CI_EMAIL --role=$r --condition=None >/dev/null
done
gcloud iam workload-identity-pools describe $GCP_POOL --location=global --project=$P >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools create $GCP_POOL --location=global --project=$P --display-name="Semana 12 GitHub"
gcloud iam workload-identity-pools providers describe github --workload-identity-pool=$GCP_POOL --location=global --project=$P >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools providers create-oidc github --workload-identity-pool=$GCP_POOL --location=global --project=$P \
    --issuer-uri=https://token.actions.githubusercontent.com \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository == '$GH_REPO'"
BASE=principal://iam.googleapis.com/projects/$NUM/locations/global/workloadIdentityPools/$GCP_POOL/subject
gcloud iam service-accounts add-iam-policy-binding $GCP_SA_CI_EMAIL --project=$P --role=roles/iam.workloadIdentityUser \
  --member="$BASE/$SUJETO" >/dev/null
# Remove the binding with the name-based subject format if it is left from an earlier run and no longer applies
[ "$SUJETO" != "repo:$GH_REPO:environment:$GH_ENTORNO" ] && gcloud iam service-accounts remove-iam-policy-binding $GCP_SA_CI_EMAIL \
  --project=$P --role=roles/iam.workloadIdentityUser --member="$BASE/repo:$GH_REPO:environment:$GH_ENTORNO" >/dev/null 2>&1 || true
echo "accepted subject: $SUJETO"
echo "provider: projects/$NUM/locations/global/workloadIdentityPools/$GCP_POOL/providers/github"
echo "service account: $GCP_SA_CI_EMAIL (user-managed keys: $(gcloud iam service-accounts keys list --iam-account=$GCP_SA_CI_EMAIL --managed-by=user --format='value(name)' | wc -l | tr -d ' '))"
