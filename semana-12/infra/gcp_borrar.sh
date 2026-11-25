#!/usr/bin/env bash
# Week 12 (Google Cloud): deletes the apps (engines), data stores, the document bucket and the week's service account.
#   ./gcp_borrar.sh                          dry run (the default)
#   ./gcp_borrar.sh --confirmar              deletes
#   ./gcp_borrar.sh --confirmar --presupuesto   also deletes the budget (after reviewing the invoice)
#   English names: --confirm = --confirmar, --budget = --presupuesto; gcp_delete.sh = this script.
# It only touches resources with the semana12 prefix in the config.sh project. Requires the owner's session (gcloud auth login).
set -uo pipefail
cd "$(dirname "$0")"; source config.sh
HAZ=0; PRES=0; for a in "$@"; do case "$a" in --confirmar|--confirm) HAZ=1 ;; --presupuesto|--budget) PRES=1 ;; esac; done
P=$GCP_PROYECTO
TOKEN=$(gcloud auth print-access-token)
API="https://discoveryengine.googleapis.com/v1/projects/$P/locations/$GCP_UBICACION/collections/default_collection"
api() { curl -s -X "$1" -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $P" "$2"; }
nombres() { python3 -c "import json,sys; d=json.load(sys.stdin); [print(x['name']) for x in d.get('$1',[]) if x['name'].split('/')[-1].startswith('$PREFIJO')]"; }
run_del() { if [ $HAZ -eq 1 ]; then echo "+ DELETE $1"; api DELETE "https://discoveryengine.googleapis.com/v1/$1" | grep -o '"name": "[^"]*' | head -1; else echo "[dry run] DELETE $1"; fi; }
run() { if [ $HAZ -eq 1 ]; then echo "+ $*"; "$@" >/dev/null 2>&1 || echo "  (failed: $*)"; else echo "[dry run] $*"; fi; }

for e in $(api GET "$API/engines" | nombres engines); do run_del "$e"; done      # apps before data stores
[ $HAZ -eq 1 ] && sleep 10
for d in $(api GET "$API/dataStores" | nombres dataStores); do run_del "$d"; done
for b in $(gcloud storage buckets list --project=$P --format='value(name)' | grep "^$PREFIJO"); do
  run gcloud storage rm --recursive gs://$b
done
gcloud iam service-accounts describe $GCP_SA_EMAIL --project=$P >/dev/null 2>&1 && \
  { run gcloud projects remove-iam-policy-binding $P --member=serviceAccount:$GCP_SA_EMAIL --role=roles/discoveryengine.editor --condition=None
    run gcloud projects remove-iam-policy-binding $P --member=serviceAccount:$GCP_SA_EMAIL --role=roles/serviceusage.serviceUsageConsumer --condition=None
    run gcloud iam service-accounts delete $GCP_SA_EMAIL --project=$P --quiet; }
# CI (activity 9): the Workload Identity pool (it stays 30 days in soft delete) and the semana12-ci service account.
gcloud iam workload-identity-pools describe $GCP_POOL --location=global --project=$P >/dev/null 2>&1 && \
  run gcloud iam workload-identity-pools delete $GCP_POOL --location=global --project=$P --quiet
gcloud iam service-accounts describe $GCP_SA_CI_EMAIL --project=$P >/dev/null 2>&1 && \
  { for r in roles/discoveryengine.viewer roles/serviceusage.serviceUsageConsumer; do
      run gcloud projects remove-iam-policy-binding $P --member=serviceAccount:$GCP_SA_CI_EMAIL --role=$r --condition=None; done
    run gcloud iam service-accounts delete $GCP_SA_CI_EMAIL --project=$P --quiet; }
if [ $PRES -eq 1 ]; then
  CTA=$(gcloud billing projects describe $P --format='value(billingAccountName.basename())')
  for b in $(gcloud billing budgets list --billing-account=$CTA --filter="displayName=$PREFIJO" --format='value(name)'); do
    run gcloud billing budgets delete $b --quiet
  done
fi
echo; ./inventario.sh gcp
