#!/usr/bin/env bash
# Week 12, activity 5 (run by the project owner): the document bucket in GCS and permissions on that bucket only.
# - the semana12-operador service account can read and write the bucket's objects (roles/storage.objectAdmin on the bucket);
# - the Discovery Engine service agent can read them to import them (roles/storage.objectViewer on the bucket).
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
P=$GCP_PROYECTO
NUM=$(gcloud projects describe $P --format='value(projectNumber)')
if ! gcloud storage buckets describe gs://$GCS_DOCS --project=$P >/dev/null 2>&1; then
  gcloud storage buckets create gs://$GCS_DOCS --project=$P --location=US --uniform-bucket-level-access \
    --public-access-prevention --default-storage-class=STANDARD
  gcloud storage buckets update gs://$GCS_DOCS --update-labels=$ETIQUETA_CLAVE=$ETIQUETA_VALOR
  echo "bucket gs://$GCS_DOCS: created (private, US)"
fi
# The Discovery Engine service agent exists once the API is enabled; its creation is forced in case it does not exist yet.
gcloud beta services identity create --service=discoveryengine.googleapis.com --project=$P --quiet >/dev/null 2>&1 || true
gcloud storage buckets add-iam-policy-binding gs://$GCS_DOCS --member=serviceAccount:$GCP_SA_EMAIL --role=roles/storage.objectAdmin >/dev/null
gcloud storage buckets add-iam-policy-binding gs://$GCS_DOCS \
  --member=serviceAccount:service-$NUM@gcp-sa-discoveryengine.iam.gserviceaccount.com --role=roles/storage.objectViewer >/dev/null
echo "permissions on gs://$GCS_DOCS: $GCP_SA (objectAdmin), Discovery Engine agent (objectViewer)"
