# Week 12: names and parameters shared by the infra scripts. No secrets: the credentials come from each
# CLI's session (aws login / the `semana12` profile; gcloud with ADC through impersonation). Loaded with `source`.
REGION=us-east-1
PREFIJO=semana12
ETIQUETA_CLAVE=proyecto
ETIQUETA_VALOR=semana12
PRESUPUESTO_USD=10
# Email for the budget alerts: taken from the environment so that it is not versioned.
ALERTA_CORREO=${ALERTA_CORREO:-$(git config user.email 2>/dev/null)}

# AWS
CUENTA_AWS=${CUENTA_AWS:-$(aws sts get-caller-identity --query Account --output text 2>/dev/null)}
S3_DOCS=${PREFIJO}-docs-${CUENTA_AWS}
S3_VECTORES=${PREFIJO}-vectores-${CUENTA_AWS}
S3_MULTIMODAL=${PREFIJO}-multimodal-${CUENTA_AWS}   # supplemental storage for multimodal BDA (the root of a bucket)
ROL_KB=${PREFIJO}-bedrock-kb
ROL_OPERADOR=${PREFIJO}-operador
PERFIL_AWS=${PREFIJO}
MODELOS_EMB=("amazon.titan-embed-text-v2:0" "cohere.embed-multilingual-v3")
PERFILES_CLAUDE=("us.anthropic.claude-haiku-4-5-20251001-v1:0" "us.anthropic.claude-haiku-5-5")
MODELOS_CLAUDE=("anthropic.claude-haiku-4-5-20251001-v1:0" "anthropic.claude-haiku-5-5")

# Google Cloud
GCP_PROYECTO=${GCP_PROYECTO:-ejemplo1-9xub}
GCP_UBICACION=global
GCS_DOCS=${PREFIJO}-docs-${GCP_PROYECTO}
GCP_SA=${PREFIJO}-operador
GCP_SA_EMAIL=${GCP_SA}@${GCP_PROYECTO}.iam.gserviceaccount.com

# CI (activity 9): the manual workflow authenticates with OIDC; only jobs of the nube-semana12 GitHub environment in this repository.
GH_REPO=mcorona/genai-engineering-lab
GH_ENTORNO=nube-semana12
ROL_CI=${PREFIJO}-ci
GCP_SA_CI=${PREFIJO}-ci
GCP_SA_CI_EMAIL=${GCP_SA_CI}@${GCP_PROYECTO}.iam.gserviceaccount.com
GCP_POOL=${PREFIJO}-github
# The subject (sub) of the OIDC token GitHub issues for the environment. If the repository uses an immutable subject (use_immutable_subject),
# the prefix carries the numeric ids of the owner and the repository (repo:owner@id/repo@id); it is read from the API so as not to hard-code it.
gh_sujeto() {
  local p; p=$(gh api repos/$GH_REPO/actions/oidc/customization/sub --jq 'if .use_immutable_subject then .sub_claim_prefix else "" end')
  echo "${p:-repo:$GH_REPO}:environment:$GH_ENTORNO"
}
