#!/usr/bin/env bash
# Week 12, activity 9: the nube-semana12 GitHub environment, deployable only from main, with the (non-secret) variables
# the manual workflow uses to federate with AWS and Google Cloud. The Anthropic and OpenAI keys are stored as
# ENVIRONMENT secrets: only a job that declares environment: nube-semana12, that is, the manual workflow, can see them.
#   ./github_entorno.sh            creates or updates the environment
#   ./github_entorno.sh --borrar   deletes it with its secrets (activity 10)
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
if [ "${1:-}" = "--borrar" ]; then   # activity 10: deletes the environment with its variables and secrets (the Anthropic and OpenAI keys)
  gh api -X DELETE repos/$GH_REPO/environments/$GH_ENTORNO && echo "environment $GH_ENTORNO: deleted (with its secrets and variables)"
  exit 0
fi
NUM=$(gcloud projects describe $GCP_PROYECTO --format='value(projectNumber)')
gh api -X PUT repos/$GH_REPO/environments/$GH_ENTORNO --input - >/dev/null <<J
{"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}
J
gh api repos/$GH_REPO/environments/$GH_ENTORNO/deployment-branch-policies --jq '.branch_policies[].name' | grep -qx main || \
  gh api -X POST repos/$GH_REPO/environments/$GH_ENTORNO/deployment-branch-policies -f name=main -f type=branch >/dev/null
gh variable set AWS_ROLE_ARN --env $GH_ENTORNO --repo $GH_REPO --body "arn:aws:iam::$CUENTA_AWS:role/$ROL_CI"
gh variable set GCP_WIF_PROVIDER --env $GH_ENTORNO --repo $GH_REPO --body "projects/$NUM/locations/global/workloadIdentityPools/$GCP_POOL/providers/github"
gh variable set GCP_SA --env $GH_ENTORNO --repo $GH_REPO --body "$GCP_SA_CI_EMAIL"
gh variable set GCP_PROYECTO --env $GH_ENTORNO --repo $GH_REPO --body "$GCP_PROYECTO"
[ -n "${ANTHROPIC_API_KEY:-}" ] && printf %s "$ANTHROPIC_API_KEY" | gh secret set ANTHROPIC_API_KEY --env $GH_ENTORNO --repo $GH_REPO
[ -n "${OPENAI_API_KEY:-}" ] && printf %s "$OPENAI_API_KEY" | gh secret set OPENAI_API_KEY --env $GH_ENTORNO --repo $GH_REPO
echo "environment $GH_ENTORNO: main only; variables:"; gh variable list --env $GH_ENTORNO --repo $GH_REPO
echo "environment secrets:"; gh secret list --env $GH_ENTORNO --repo $GH_REPO
