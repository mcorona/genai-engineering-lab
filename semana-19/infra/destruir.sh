#!/usr/bin/env bash
# Week 19, activity 3: tears the foundation stacks down, then checks that nothing is left (except the explicit list).
#
#   semana-19/infra/destruir.sh                 simulation: prints the order and what would be removed. No AWS calls.
#   semana-19/infra/destruir.sh --inventario    read-only: runs the inventory with the read-only profile.
#   semana-19/infra/destruir.sh --si            acts: destroys semana19-base, then the bootstrap, then checks.
#   semana-19/infra/destruir.sh --si --todo     also deletes semana19-control (budget, action, roles, policies).
#
# Without --todo the control stack stays (it is $0/h) and the inventory allows it explicitly.
# The bootstrap KMS key is scheduled for deletion by its stack (CloudFormation default window, 30 days; D,
# pending-deletion keys are not billed per the KMS pricing page). The base key uses the 7-day window of lab.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PERFIL_ADMIN="${S19_PERFIL_ADMIN:-manuel-admin}"
PERFIL_DESPLIEGUE="${S19_PERFIL_DESPLIEGUE:-semana19-despliegue}"
PERFIL_LECTURA="${S19_PERFIL_LECTURA:-semana19-lectura}"
PYTHON_CDK="${S19_PYTHON:-$RAIZ/.venv-cdk/bin/python}"
PYTHON_BOTO="${S19_PYTHON_BOTO:-$RAIZ/.venv/bin/python}"  # boto3: inventario y vaciado (venv-cdk no lo tiene)
APP="$RAIZ/semana-19/infra/cdk/app.py"
REGISTRO="$RAIZ/semana-19/resultados/tiempos_despliegue.jsonl"
REGION="us-east-1"
MODO="simulacion"
TODO=0

for argumento in "$@"; do
  case "$argumento" in
    --si) MODO="si" ;;
    --inventario) MODO="inventario" ;;
    --todo) TODO=1 ;;
    *) echo "argumento no reconocido: $argumento" >&2; exit 2 ;;
  esac
done
if [[ "$TODO" == "1" && "$MODO" != "si" ]]; then
  echo "--todo solo tiene efecto con --si." >&2
  exit 2
fi

registrar() {
  local paso="$1" segundos="$2"
  printf '{"fecha": "%s", "paso": "%s", "segundos": %s, "modo": "%s"}\n' \
    "$(date +%Y-%m-%d)" "$paso" "$segundos" "destruir-$MODO" >> "$REGISTRO"
}

inventario() {
  local con_control="--con-control"
  if [[ "$TODO" == "1" ]]; then con_control=""; fi
  # shellcheck disable=SC2086
  "$PYTHON_BOTO" "$RAIZ/semana-19/infra/inventario.py" --perfil "$PERFIL_LECTURA" --region "$REGION" $con_control
}

if [[ "$MODO" == "simulacion" ]]; then
  echo "== Simulación. No se llamó a AWS."
  echo "1) cdk destroy semana19-base            (perfil de despliegue; borrar sigue permitido con la congelación)"
  echo "2) vaciar el bucket y el ECR del bootstrap  (vaciar_bootstrap.py --si, perfil admin)"
  echo "3) aws cloudformation delete-stack semana19-cdktoolkit  (perfil admin; programa el borrado de la llave del bootstrap)"
  if [[ "$TODO" == "1" ]]; then
    echo "4) aws cloudformation delete-stack semana19-control  (perfil admin)"
  else
    echo "4) semana19-control se queda (no se pasó --todo)"
  fi
  echo "5) inventario (solo lectura): solo se permite lo listado en inventario.py::permitidos"
  echo "Para el inventario sin borrar nada: destruir.sh --inventario. Para actuar: destruir.sh --si, con tu OK."
  exit 0
fi

if [[ "$MODO" == "inventario" ]]; then
  inventario
  exit $?
fi

# --- MODO si
existe_stack() {
  aws cloudformation describe-stacks --stack-name "$1" --region "$REGION" --profile "$PERFIL_ADMIN" \
    --query "Stacks[0].StackStatus" --output text >/dev/null 2>&1
}

ESTADO_BASE="$(aws cloudformation describe-stacks --stack-name semana19-base --region "$REGION" --profile "$PERFIL_ADMIN" \
  --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo NO_EXISTE)"
if [[ "$ESTADO_BASE" == "DELETE_FAILED" ]]; then
  # Known case (2026-11-13): the custom resource that restricts the default SG cannot be deleted, because its Lambda
  # role has no Authorize* rights under the permissions boundary. It is an AWS-less CloudFormation resource: retaining
  # it leaves nothing in the account. Only that resource is retained; the rest of the stack is deleted.
  echo "== Paso 1b: semana19-base en DELETE_FAILED: se retiene solo el custom resource del SG por defecto"
  inicio=$(date +%s)
  retenidos="$(aws cloudformation describe-stack-events --stack-name semana19-base --region "$REGION" --profile "$PERFIL_ADMIN" \
    --query "StackEvents[?ResourceStatus=='DELETE_FAILED' && ResourceType=='Custom::VpcRestrictDefaultSG'].LogicalResourceId" \
    --output text | tr '\t' '\n' | sort -u | paste -sd, -)"
  if [[ -z "$retenidos" ]]; then
    echo "No se identificó el custom resource fallido; revisa los eventos del stack antes de continuar." >&2
    exit 1
  fi
  aws cloudformation delete-stack --stack-name semana19-base --region "$REGION" --profile "$PERFIL_ADMIN" \
    --retain-resources "$retenidos"
  aws cloudformation wait stack-delete-complete --stack-name semana19-base --region "$REGION" --profile "$PERFIL_ADMIN"
  registrar "destruir-base-retenido" $(( $(date +%s) - inicio ))
elif [[ "$ESTADO_BASE" != "NO_EXISTE" ]]; then
  inicio=$(date +%s)
  echo "== Paso 1: cdk destroy semana19-base"
  cdk destroy semana19-base --force --app "$PYTHON_CDK $APP" --profile "$PERFIL_DESPLIEGUE" --region "$REGION"
  registrar "destruir-base" $(( $(date +%s) - inicio ))
else
  echo "== Paso 1: semana19-base no existe"
fi

if existe_stack semana19-cdktoolkit; then
  echo "== Paso 2: vaciar el bucket y el ECR del bootstrap"
  "$PYTHON_BOTO" "$RAIZ/semana-19/infra/vaciar_bootstrap.py" --perfil "$PERFIL_ADMIN" --region "$REGION" --si
  inicio=$(date +%s)
  echo "== Paso 3: borrar semana19-cdktoolkit (programa el borrado de su llave KMS)"
  aws cloudformation delete-stack --stack-name semana19-cdktoolkit --region "$REGION" --profile "$PERFIL_ADMIN"
  aws cloudformation wait stack-delete-complete --stack-name semana19-cdktoolkit --region "$REGION" --profile "$PERFIL_ADMIN"
  registrar "destruir-bootstrap" $(( $(date +%s) - inicio ))
else
  echo "== Paso 2-3: semana19-cdktoolkit no existe"
fi

if [[ "$TODO" == "1" ]] && existe_stack semana19-control; then
  inicio=$(date +%s)
  echo "== Paso 4: borrar semana19-control"
  aws cloudformation delete-stack --stack-name semana19-control --region "$REGION" --profile "$PERFIL_ADMIN"
  aws cloudformation wait stack-delete-complete --stack-name semana19-control --region "$REGION" --profile "$PERFIL_ADMIN"
  registrar "destruir-control" $(( $(date +%s) - inicio ))
fi

echo "== Paso 5: inventario (solo lectura)"
set +e
inventario
codigo=$?
set -e
if [[ "$codigo" -ne 0 ]]; then
  echo "El inventario encontró algo fuera de la lista permitida. Revisa 'inesperados' antes de dar por terminado." >&2
  exit "$codigo"
fi
echo "== Inventario limpio: solo lo permitido."
