#!/usr/bin/env bash
# Week 19, activity 3: deploys the foundation stacks (semana19-control, then the bootstrap, then semana19-base).
#
#   semana-19/infra/desplegar.sh            simulation: synthesizes locally and prints the plan. No AWS calls.
#   semana-19/infra/desplegar.sh --diff     read-only: compares with what is deployed. No changes.
#   semana-19/infra/desplegar.sh --si       acts. Only after Manuel's OK for the exact plan shown by --diff.
#   English names: deploy.sh runs this script; --yes = --si, --control-only = --solo-control.
#   add --solo-control to --diff or --si: only semana19-control and the bootstrap (steps 1 and 2); base, datos, ia, the
#   loader and the ingestion are not touched. For changes to the budget, the boundary or the execution policies.
#
# Environment:
#   PERFIL=lab|prod                  profile in semana-19/spike/perfiles.json (default lab; only lab is deployed)
#   S19_PERFIL_ADMIN                 admin profile, aws login (default manuel-admin)
#   S19_PERFIL_DESPLIEGUE            profile that assumes semana19-despliegue (default semana19-despliegue)
#   S19_PYTHON                       python with aws-cdk-lib 2.276.0 (default: .venv-cdk of the worktree)
#   ALERTA_EMAIL                     alert address, from the environment only; never written to the repo. With
#                                    --solo-control and semana19-control deployed, it may be left unset: the stack
#                                    keeps its CorreoAlerta (CloudFormation reuses a parameter that is not overridden)
#   S19_BUCKET_PLANTILLAS            temporary S3 bucket to stage the control template (> 51,200 bytes); created and
#                                    deleted by the operator, never written to the repo
#
# The account ID never appears in this file or in its output: it is resolved at run time and printed as <account>.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP="$RAIZ/semana-19/infra/cdk/app.py"
REGISTRO="$RAIZ/semana-19/resultados/tiempos_despliegue.jsonl"
PERFIL_ADMIN="${S19_PERFIL_ADMIN:-manuel-admin}"
PERFIL_DESPLIEGUE="${S19_PERFIL_DESPLIEGUE:-semana19-despliegue}"
PYTHON_CDK="${S19_PYTHON:-$RAIZ/.venv-cdk/bin/python}"
REGION="us-east-1"
PERFIL="${PERFIL:-lab}"
MODO="simulacion"
SOLO_CONTROL=0

for argumento in "$@"; do
  case "$argumento" in
    --si|--yes) MODO="si" ;;
    --diff) MODO="diff" ;;
    --solo-control|--control-only) SOLO_CONTROL=1 ;;
    *) echo "unrecognized argument: $argumento (use --diff or --si; with no argument it simulates)" >&2; exit 2 ;;
  esac
done

if [[ "$PERFIL" != "lab" ]]; then
  echo "Activity 3 deploys only the lab profile (PERFIL=$PERFIL)." >&2
  exit 2
fi

# Activity 9, 2026-11-21: semana19-computo imports exports of base, datos and ia that only a COMPUTO=1 synth creates.
# Deployed without it, computo failed ("No export named semana19-datos:..."); and once computo imports them, a deploy
# without it would try to remove exports in use. The foundation is synthesized and deployed the way destruir.sh destroys
# it. The synth needs the agent package (python3 semana-19/infra/paquete_agente.py) and stops at step 0 without it.
export COMPUTO=1

OUT="$(mktemp -d "${TMPDIR:-/tmp}/s19-desplegar.XXXXXX")"
trap 'rm -rf "$OUT"' EXIT

sintetizar() {
  PERFIL="$PERFIL" CDK_OUTDIR="$OUT" "$PYTHON_CDK" "$APP" >/dev/null
}

registrar() {
  # One JSON line per measured step: name, seconds and date. Only real runs write here.
  local paso="$1" segundos="$2"
  printf '{"fecha": "%s", "paso": "%s", "segundos": %s, "modo": "%s"}\n' \
    "$(date +%Y-%m-%d)" "$paso" "$segundos" "$MODO" >> "$REGISTRO"
}

existe_stack() {
  aws cloudformation describe-stacks --stack-name "$1" --region "$REGION" --profile "$2" \
    --query "Stacks[0].StackStatus" --output text >/dev/null 2>&1
}

echo "== Step 0: synthesize (local, no AWS)"
sintetizar
echo "   templates: $(ls "$OUT" | grep -c 'template.json') in the temporary folder"

if [[ "$MODO" == "simulacion" ]]; then
  echo
  echo "== Simulation. No AWS calls were made."
  echo "Order: 1) semana19-control (aws cloudformation deploy)  2) bootstrap s19 (cdk bootstrap)  3) semana19-base (cdk deploy)  4) semana19-datos (cdk deploy)"
  for plantilla in semana19-control semana19-base; do
    echo "-- $plantilla: resources by type"
    "$PYTHON_CDK" - "$OUT/$plantilla.template.json" <<'PY'
import collections, json, sys
t = json.load(open(sys.argv[1], encoding="utf-8"))
c = collections.Counter(r["Type"] for r in t["Resources"].values())
for tipo, n in sorted(c.items()):
    print(f"   {n:3d}  {tipo}")
PY
  done
  echo
  echo "To see what would change against what is deployed: desplegar.sh --diff (read-only)."
  echo "To act: desplegar.sh --si, only after your OK on that diff."
  exit 0
fi

if [[ "$MODO" == "diff" ]]; then
  echo
  echo "== Read-only diff"
  if existe_stack semana19-control "$PERFIL_ADMIN"; then
    aws cloudformation get-template --stack-name semana19-control --region "$REGION" --profile "$PERFIL_ADMIN" \
      --query TemplateBody --output json > "$OUT/control_desplegada.json"
    "$PYTHON_CDK" - "$OUT/control_desplegada.json" "$OUT/semana19-control.template.json" <<'PY'
import json, sys
viejo = json.load(open(sys.argv[1], encoding="utf-8"))
nuevo = json.load(open(sys.argv[2], encoding="utf-8"))
vr, nr = set(viejo.get("Resources", {})), set(nuevo.get("Resources", {}))
sin_metadata = lambda r: {k: v for k, v in r.items() if k != "Metadata"}  # synth notes (cdk-nag, paths), not a change
print(f"-- semana19-control: create {sorted(nr - vr)}, remove {sorted(vr - nr)}, "
      f"change {sorted(k for k in vr & nr if sin_metadata(viejo['Resources'][k]) != sin_metadata(nuevo['Resources'][k]))}")
PY
  else
    echo "-- semana19-control: does not exist; it would be created with $(grep -o '"Type": "AWS::[A-Za-z0-9:]*"' "$OUT/semana19-control.template.json" | wc -l | tr -d ' ') resources"
  fi
  if existe_stack semana19-cdktoolkit "$PERFIL_ADMIN"; then
    echo "-- bootstrap s19: already exists"
  else
    echo "-- bootstrap s19: does not exist; it would be created (17 resource types, a KMS key at 1.00 USD/month)"
  fi
  if [[ "$SOLO_CONTROL" == 1 ]]; then exit 0; fi
  echo "-- semana19-base: CDK diff"
  if aws configure list-profiles 2>/dev/null | grep -qx "$PERFIL_DESPLIEGUE"; then
    cdk diff semana19-base --app "$PYTHON_CDK $APP" --profile "$PERFIL_DESPLIEGUE" --region "$REGION"
  else
    echo "   no profile '$PERFIL_DESPLIEGUE' in ~/.aws/config: the semana19-base diff is done"
    echo "   after the profile is created (step 5 of the guide). It is not estimated here."
  fi
  echo "-- semana19-ia (guardrail, activity 5): CDK diff"
  if aws configure list-profiles 2>/dev/null | grep -qx "$PERFIL_DESPLIEGUE"; then
    cdk diff semana19-ia --app "$PYTHON_CDK $APP" --profile "$PERFIL_DESPLIEGUE" --region "$REGION"
  else
    echo "   no profile '$PERFIL_DESPLIEGUE': the semana19-ia diff is done after the profile is created."
  fi
  exit 0
fi

# --- MODO si: acts. The caller already approved the plan shown by --diff.
CORREO_PREVIO=0
if [[ -z "${ALERTA_EMAIL:-}" ]]; then
  if [[ "$SOLO_CONTROL" == 1 ]] && existe_stack semana19-control "$PERFIL_ADMIN"; then
    CORREO_PREVIO=1
    echo "== ALERTA_EMAIL is not in the environment: semana19-control keeps its CorreoAlerta (not printed)."
  else
    echo "ALERTA_EMAIL is missing from the environment (the address is never stored in the repository)." >&2
    exit 2
  fi
fi
# Budgets rejects a malformed address only after CloudFormation has started, and the rollback can stick (2026-11-21:
# ROLLBACK_FAILED on semana19-limite). The shape is checked here, before any AWS call; the address is never printed.
if [[ -n "${ALERTA_EMAIL:-}" && ! "$ALERTA_EMAIL" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]]; then
  echo "ALERTA_EMAIL is not shaped like an email address (one @ and a domain with a dot, no spaces); it is not printed." >&2
  exit 2
fi

CUENTA="$(aws sts get-caller-identity --profile "$PERFIL_ADMIN" --query Account --output text)"
echo "== Account: <account> (resolved at run time, not printed)"

# The control template is larger than 51,200 bytes, so CloudFormation needs an S3 bucket to stage it. The bootstrap
# bucket does not exist yet at this step (the bootstrap trusts the role this stack creates). S19_BUCKET_PLANTILLAS names
# a temporary bucket created by the operator and deleted after the run; it is never written to the repo.
desplegar_control() {
  local bootstrap_creado="$1"
  local bucket=()
  local parametros=("BootstrapCreado=$bootstrap_creado")
  if [[ "$CORREO_PREVIO" == 0 ]]; then parametros=("CorreoAlerta=$ALERTA_EMAIL" "${parametros[@]}"); fi
  if [ -n "${S19_BUCKET_PLANTILLAS:-}" ]; then
    bucket=(--s3-bucket "$S19_BUCKET_PLANTILLAS")
  elif [[ "$bootstrap_creado" == "true" ]]; then
    # Once the bootstrap exists, its staging bucket holds the template (CloudFormation reads it from there).
    bucket=(--s3-bucket "$(aws cloudformation describe-stacks --stack-name semana19-cdktoolkit --region "$REGION" \
      --profile "$PERFIL_ADMIN" --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" --output text)")
  fi
  aws cloudformation deploy --stack-name semana19-control --region "$REGION" --profile "$PERFIL_ADMIN" \
    --template-file "$OUT/semana19-control.template.json" --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides "${parametros[@]}" \
    --no-fail-on-empty-changeset ${bucket[@]+"${bucket[@]}"}
}

BOOTSTRAP_ANTES="false"
if existe_stack semana19-cdktoolkit "$PERFIL_ADMIN"; then BOOTSTRAP_ANTES="true"; fi

inicio=$(date +%s)
echo "== Step 1: semana19-control (no assets, through the CLI; BootstrapCreado=$BOOTSTRAP_ANTES)"
desplegar_control "$BOOTSTRAP_ANTES"
registrar "control" $(( $(date +%s) - inicio ))

ARN_DESPLIEGUE="$(aws cloudformation describe-stacks --stack-name semana19-control --region "$REGION" \
  --profile "$PERFIL_ADMIN" --query "Stacks[0].Outputs[?OutputKey=='ArnDespliegue'].OutputValue" --output text)"
ARN_EJECUCION="$(aws cloudformation describe-stacks --stack-name semana19-control --region "$REGION" \
  --profile "$PERFIL_ADMIN" --query "Stacks[0].Outputs[?OutputKey=='ArnEjecucionCfn'].OutputValue" --output text)"
ARN_EJECUCION_IA="$(aws cloudformation describe-stacks --stack-name semana19-control --region "$REGION" \
  --profile "$PERFIL_ADMIN" --query "Stacks[0].Outputs[?OutputKey=='ArnEjecucionCfnIa'].OutputValue" --output text)"
ARN_EJECUCION_DATOS="$(aws cloudformation describe-stacks --stack-name semana19-control --region "$REGION" \
  --profile "$PERFIL_ADMIN" --query "Stacks[0].Outputs[?OutputKey=='ArnEjecucionCfnDatos'].OutputValue" --output text)"
ARN_EJECUCION_COMPUTO="$(aws cloudformation describe-stacks --stack-name semana19-control --region "$REGION" \
  --profile "$PERFIL_ADMIN" --query "Stacks[0].Outputs[?OutputKey=='ArnEjecucionCfnComputo'].OutputValue" --output text)"
ARN_EJECUCION_AGENTES="$(aws cloudformation describe-stacks --stack-name semana19-control --region "$REGION" \
  --profile "$PERFIL_ADMIN" --query "Stacks[0].Outputs[?OutputKey=='ArnEjecucionCfnAgentes'].OutputValue" --output text)"

# The bootstrap is applied on every run: it is idempotent and keeps the execution role's policy list current
# (semana19-cfn-exec for base and control, semana19-cfn-exec-datos for datos, semana19-cfn-exec-ia for ia,
# semana19-cfn-exec-computo for computo, semana19-cfn-exec-agentes for the gateway and the comparison agent).
inicio=$(date +%s)
if existe_stack semana19-cdktoolkit "$PERFIL_ADMIN"; then
  echo "== Step 2: bootstrap s19 (updates the execution role's policy list)"
else
  echo "== Step 2: bootstrap s19 (creates it; it trusts only ${ARN_DESPLIEGUE//$CUENTA/<account>})"
fi
cdk bootstrap "aws://$CUENTA/$REGION" --profile "$PERFIL_ADMIN" --qualifier s19 \
  --toolkit-stack-name semana19-cdktoolkit \
  --cloudformation-execution-policies "$ARN_EJECUCION,$ARN_EJECUCION_DATOS,$ARN_EJECUCION_IA,$ARN_EJECUCION_COMPUTO,$ARN_EJECUCION_AGENTES" \
  --trust "$ARN_DESPLIEGUE" 2>&1 | sed "s/$CUENTA/<account>/g"  # cdk prints the account in its ARNs
registrar "bootstrap" $(( $(date +%s) - inicio ))
if [[ "$SOLO_CONTROL" == 1 ]]; then
  echo "== Done (--solo-control): semana19-control and the bootstrap. Base, datos and ia were not touched."
  exit 0
fi

inicio=$(date +%s)
echo "== Step 3: semana19-base (time to CREATE_COMPLETE measured)"
cdk deploy semana19-base --app "$PYTHON_CDK $APP" --profile "$PERFIL_DESPLIEGUE" --region "$REGION" \
  --toolkit-stack-name semana19-cdktoolkit --require-approval never
registrar "base" $(( $(date +%s) - inicio ))

inicio=$(date +%s)
echo "== Step 4: semana19-datos (PostgreSQL database, activity 4)"
cdk deploy semana19-datos --app "$PYTHON_CDK $APP" --profile "$PERFIL_DESPLIEGUE" --region "$REGION" \
  --toolkit-stack-name semana19-cdktoolkit --require-approval never
registrar "datos" $(( $(date +%s) - inicio ))

inicio=$(date +%s)
echo "== Step 4b: semana19-ia (the guardrail with its tier, activity 5)"
cdk deploy semana19-ia --app "$PYTHON_CDK $APP" --profile "$PERFIL_DESPLIEGUE" --region "$REGION" \
  --toolkit-stack-name semana19-cdktoolkit --require-approval never
registrar "ia" $(( $(date +%s) - inicio ))

# Step 5 (--si only): the loader puts the seed and the dictionary documents in place, then the knowledge base
# ingestion job runs on them. The ingestion job is not a CloudFormation resource, so it is started here by API.
inicio=$(date +%s)
echo "== Step 5: load the database and start the KB ingestion (outside CloudFormation)"
SALIDAS_DATOS="$(aws cloudformation describe-stacks --stack-name semana19-datos --region "$REGION" \
  --profile "$PERFIL_ADMIN" --query "Stacks[0].Outputs" --output json)"
EVENTO_CARGA="$(printf '%s' "$SALIDAS_DATOS" | "$PYTHON_CDK" -c 'import json,sys
o={x["OutputKey"]:x["OutputValue"] for x in json.load(sys.stdin)}
print(json.dumps({"secret_arn":o["ArnSecretoBd"],"db_host":o["HostBd"],"docs_bucket":o["BucketDocsKb"]}))')"
NOMBRE_CARGADOR="$(printf '%s' "$SALIDAS_DATOS" | "$PYTHON_CDK" -c 'import json,sys
print({x["OutputKey"]:x["OutputValue"] for x in json.load(sys.stdin)}["NombreCargador"])')"
KB_ID="$(printf '%s' "$SALIDAS_DATOS" | "$PYTHON_CDK" -c 'import json,sys
print({x["OutputKey"]:x["OutputValue"] for x in json.load(sys.stdin)}["KbId"])')"
FUENTE_ID="$(printf '%s' "$SALIDAS_DATOS" | "$PYTHON_CDK" -c 'import json,sys
print({x["OutputKey"]:x["OutputValue"] for x in json.load(sys.stdin)}["DataSourceId"])')"
SALIDA_CARGA="$(mktemp "${TMPDIR:-/tmp}/cargador.XXXXXX")"
ERROR_FUNCION="$(aws lambda invoke --function-name "$NOMBRE_CARGADOR" --region "$REGION" --profile "$PERFIL_ADMIN" \
  --cli-binary-format raw-in-base64-out --payload "$EVENTO_CARGA" --query FunctionError --output text "$SALIDA_CARGA")"
if [[ "$ERROR_FUNCION" != "None" ]]; then
  echo "The loader failed; the ingestion is not started. Output:" >&2; cat "$SALIDA_CARGA" >&2; exit 1
fi
cat "$SALIDA_CARGA"; echo
rm -f "$SALIDA_CARGA"
TRABAJO_INGESTA="$(aws bedrock-agent start-ingestion-job --knowledge-base-id "$KB_ID" --data-source-id "$FUENTE_ID" \
  --region "$REGION" --profile "$PERFIL_ADMIN" --query "ingestionJob.ingestionJobId" --output text)"
echo "Ingestion started: $TRABAJO_INGESTA (status: aws bedrock-agent get-ingestion-job)"
registrar "cargar-e-ingerir" $(( $(date +%s) - inicio ))

echo "== Done. Check with the inventory (read-only) before the next session."
