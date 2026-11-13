#!/usr/bin/env bash
# Week 19, activity 3: deploys the foundation stacks (semana19-control, then the bootstrap, then semana19-base).
#
#   semana-19/infra/desplegar.sh            simulation: synthesizes locally and prints the plan. No AWS calls.
#   semana-19/infra/desplegar.sh --diff     read-only: compares with what is deployed. No changes.
#   semana-19/infra/desplegar.sh --si       acts. Only after Manuel's OK for the exact plan shown by --diff.
#
# Environment:
#   PERFIL=lab|prod                  profile in semana-19/spike/perfiles.json (default lab; only lab is deployed)
#   S19_PERFIL_ADMIN                 admin profile, aws login (default manuel-admin)
#   S19_PERFIL_DESPLIEGUE            profile that assumes semana19-despliegue (default semana19-despliegue)
#   S19_PYTHON                       python with aws-cdk-lib 2.276.0 (default: .venv-cdk of the worktree)
#   ALERTA_EMAIL                     alert address, from the environment only; never written to the repo
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

for argumento in "$@"; do
  case "$argumento" in
    --si) MODO="si" ;;
    --diff) MODO="diff" ;;
    *) echo "argumento no reconocido: $argumento (usa --diff o --si; sin nada simula)" >&2; exit 2 ;;
  esac
done

if [[ "$PERFIL" != "lab" ]]; then
  echo "Solo se despliega el perfil lab en la actividad 3 (PERFIL=$PERFIL)." >&2
  exit 2
fi

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

echo "== Paso 0: sintetizar (local, sin AWS)"
sintetizar
echo "   plantillas: $(ls "$OUT" | grep -c 'template.json') en la carpeta temporal"

if [[ "$MODO" == "simulacion" ]]; then
  echo
  echo "== Simulación. No se llamó a AWS."
  echo "Orden: 1) semana19-control (aws cloudformation deploy)  2) bootstrap s19 (cdk bootstrap)  3) semana19-base (cdk deploy)"
  for plantilla in semana19-control semana19-base; do
    echo "-- $plantilla: recursos por tipo"
    "$PYTHON_CDK" - "$OUT/$plantilla.template.json" <<'PY'
import collections, json, sys
t = json.load(open(sys.argv[1], encoding="utf-8"))
c = collections.Counter(r["Type"] for r in t["Resources"].values())
for tipo, n in sorted(c.items()):
    print(f"   {n:3d}  {tipo}")
PY
  done
  echo
  echo "Para ver lo que cambiaría frente a lo desplegado: desplegar.sh --diff (solo lectura)."
  echo "Para actuar: desplegar.sh --si, solo después de tu OK sobre ese diff."
  exit 0
fi

if [[ "$MODO" == "diff" ]]; then
  echo
  echo "== Diff de solo lectura"
  if existe_stack semana19-control "$PERFIL_ADMIN"; then
    aws cloudformation get-template --stack-name semana19-control --region "$REGION" --profile "$PERFIL_ADMIN" \
      --query TemplateBody --output json > "$OUT/control_desplegada.json"
    "$PYTHON_CDK" - "$OUT/control_desplegada.json" "$OUT/semana19-control.template.json" <<'PY'
import json, sys
viejo = json.load(open(sys.argv[1], encoding="utf-8"))
nuevo = json.load(open(sys.argv[2], encoding="utf-8"))
vr, nr = set(viejo.get("Resources", {})), set(nuevo.get("Resources", {}))
print(f"-- semana19-control: crear {sorted(nr - vr)}, quitar {sorted(vr - nr)}, "
      f"cambiar {sorted(k for k in vr & nr if viejo['Resources'][k] != nuevo['Resources'][k])}")
PY
  else
    echo "-- semana19-control: no existe; se crearía con $(grep -o '"Type": "AWS::[A-Za-z0-9:]*"' "$OUT/semana19-control.template.json" | wc -l | tr -d ' ') recursos"
  fi
  if existe_stack semana19-cdktoolkit "$PERFIL_ADMIN"; then
    echo "-- bootstrap s19: ya existe"
  else
    echo "-- bootstrap s19: no existe; se crearía (17 tipos de recurso, llave KMS 1.00 USD/mes)"
  fi
  echo "-- semana19-base: diff de CDK"
  if aws configure list-profiles 2>/dev/null | grep -qx "$PERFIL_DESPLIEGUE"; then
    cdk diff semana19-base --app "$PYTHON_CDK $APP" --profile "$PERFIL_DESPLIEGUE" --region "$REGION"
  else
    echo "   no hay perfil '$PERFIL_DESPLIEGUE' en ~/.aws/config: el diff de semana19-base se hace"
    echo "   después de crear el perfil (paso 5 de la guía). No se estima aquí."
  fi
  exit 0
fi

# --- MODO si: acts. The caller already approved the plan shown by --diff.
if [[ -z "${ALERTA_EMAIL:-}" ]]; then
  echo "Falta ALERTA_EMAIL en el entorno (el correo no se guarda en el repo)." >&2
  exit 2
fi

CUENTA="$(aws sts get-caller-identity --profile "$PERFIL_ADMIN" --query Account --output text)"
echo "== Cuenta: <account> (resuelta en ejecución, no se imprime)"

desplegar_control() {
  local bootstrap_creado="$1"
  aws cloudformation deploy --stack-name semana19-control --region "$REGION" --profile "$PERFIL_ADMIN" \
    --template-file "$OUT/semana19-control.template.json" --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides "CorreoAlerta=$ALERTA_EMAIL" "BootstrapCreado=$bootstrap_creado" \
    --no-fail-on-empty-changeset
}

BOOTSTRAP_ANTES="false"
if existe_stack semana19-cdktoolkit "$PERFIL_ADMIN"; then BOOTSTRAP_ANTES="true"; fi

inicio=$(date +%s)
echo "== Paso 1: semana19-control (sin assets, por CLI; BootstrapCreado=$BOOTSTRAP_ANTES)"
desplegar_control "$BOOTSTRAP_ANTES"
registrar "control" $(( $(date +%s) - inicio ))

ARN_DESPLIEGUE="$(aws cloudformation describe-stacks --stack-name semana19-control --region "$REGION" \
  --profile "$PERFIL_ADMIN" --query "Stacks[0].Outputs[?OutputKey=='ArnDespliegue'].OutputValue" --output text)"
ARN_EJECUCION="$(aws cloudformation describe-stacks --stack-name semana19-control --region "$REGION" \
  --profile "$PERFIL_ADMIN" --query "Stacks[0].Outputs[?OutputKey=='ArnEjecucionCfn'].OutputValue" --output text)"

if ! existe_stack semana19-cdktoolkit "$PERFIL_ADMIN"; then
  inicio=$(date +%s)
  echo "== Paso 2: bootstrap s19 (confía solo en $ARN_DESPLIEGUE)"
  cdk bootstrap "aws://$CUENTA/$REGION" --profile "$PERFIL_ADMIN" --qualifier s19 \
    --toolkit-stack-name semana19-cdktoolkit \
    --cloudformation-execution-policies "$ARN_EJECUCION" \
    --trust "$ARN_DESPLIEGUE"
  registrar "bootstrap" $(( $(date +%s) - inicio ))
  echo "== Paso 2b: congelación también de los roles cdk-s19-* (BootstrapCreado=true)"
  desplegar_control "true"
else
  echo "== Paso 2: bootstrap s19 ya existe; no se toca"
fi

inicio=$(date +%s)
echo "== Paso 3: semana19-base (CREATE_COMPLETE medido)"
cdk deploy semana19-base --app "$PYTHON_CDK $APP" --profile "$PERFIL_DESPLIEGUE" --region "$REGION" \
  --toolkit-stack-name semana19-cdktoolkit --require-approval never
registrar "base" $(( $(date +%s) - inicio ))

echo "== Listo. Verifica con el inventario (solo lectura) antes de la siguiente sesión."
