#!/usr/bin/env bash
# Week 19, activity 3: tears the foundation stacks down, then checks that nothing is left (except the explicit list).
#
#   semana-19/infra/destruir.sh                 simulation: prints the order and what would be removed. No AWS calls.
#   semana-19/infra/destruir.sh --inventario    read-only: runs the inventory with the read-only profile.
#   semana-19/infra/destruir.sh --si            acts: destroys semana19-base, then the bootstrap, then checks.
#   semana-19/infra/destruir.sh --si --todo     also deletes semana19-control (budget, action, roles, policies).
#   semana-19/infra/destruir.sh --si --solo-actividad7
#                                               activity 7 only: the comparison agent, then the gateway, then the
#                                               inventory of their categories (they must be empty). The rest stays.
#
# Order with --si: semana19-agentes-comparacion, semana19-gateway, the judge's semana19-eval (activity 8: first its
# bucket is emptied and its evaluation jobs deleted, vaciar_eval.py with the admin profile) and semana19-computo
# (activities 6 to 8, they import the base, datos and ia exports), then datos, ia, base and the bootstrap.
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
SOLO_A7=0

for argumento in "$@"; do
  case "$argumento" in
    --si) MODO="si" ;;
    --inventario) MODO="inventario" ;;
    --todo) TODO=1 ;;
    --solo-actividad7) SOLO_A7=1 ;;
    *) echo "argumento no reconocido: $argumento" >&2; exit 2 ;;
  esac
done
if [[ "$TODO" == "1" && "$MODO" != "si" ]]; then
  echo "--todo solo tiene efecto con --si." >&2
  exit 2
fi
if [[ "$SOLO_A7" == "1" && "$TODO" == "1" ]]; then
  echo "--solo-actividad7 y --todo no se combinan." >&2
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
  echo "00a) cdk destroy semana19-agentes-comparacion  (actividad 7, desechable: primero)"
  echo "00b) cdk destroy semana19-gateway              (actividad 7: gateway, target, políticas y motor)"
  if [[ "$SOLO_A7" == "1" ]]; then
    echo "00z) inventario de las categorías de la actividad 7 (deben quedar en cero); el resto se queda"
    exit 0
  fi
  echo "00c1) vaciar el bucket del juez y borrar sus trabajos  (vaciar_eval.py --si, perfil admin; actividad 8)"
  echo "00c2) cdk destroy semana19-eval              (actividad 8: bucket y rol del juez)"
  echo "00c) cdk destroy semana19-computo              (actividad 6: agente, API, aprobación, usuarios)"
  echo "0b) cdk destroy semana19-ia              (Guardrail y prompts; antes que la red porque importa la llave)"
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

# The stacks of activities 6 and 7 exist in the app only with COMPUTO=1; the destroy needs no agent package.
destruir_pila_computo() {
  local pila="$1" paso="$2" inicio
  if existe_stack "$pila"; then
    inicio=$(date +%s)
    echo "== $paso: cdk destroy $pila"
    COMPUTO=1 S19_SIN_DEPENDENCIAS=1 cdk destroy "$pila" --exclusively --force --app "$PYTHON_CDK $APP" \
      --profile "$PERFIL_DESPLIEGUE" --region "$REGION"
    registrar "destruir-${pila#semana19-}" $(( $(date +%s) - inicio ))
  else
    echo "== $paso: $pila no existe"
  fi
}

destruir_pila_computo semana19-agentes-comparacion "Paso 00a"
destruir_pila_computo semana19-gateway "Paso 00b"
if [[ "$SOLO_A7" == "1" ]]; then
  echo "== Paso 00z: inventario de la actividad 7 (solo lectura)"
  "$PYTHON_BOTO" "$RAIZ/semana-19/infra/inventario.py" --perfil "$PERFIL_LECTURA" --region "$REGION" --solo-actividad7
  exit $?
fi
echo "== Paso 00c1: vaciar el bucket del juez y borrar sus trabajos de evaluación (actividad 8)"
"$PYTHON_BOTO" "$RAIZ/semana-19/infra/vaciar_eval.py" --perfil "$PERFIL_ADMIN" --region "$REGION" --si
destruir_pila_computo semana19-eval "Paso 00c2"
destruir_pila_computo semana19-computo "Paso 00c"

if existe_stack semana19-datos; then
  inicio=$(date +%s)
  echo "== Paso 0: cdk destroy semana19-datos (base PostgreSQL) antes que la red"
  cdk destroy semana19-datos --force --app "$PYTHON_CDK $APP" --profile "$PERFIL_DESPLIEGUE" --region "$REGION"
  registrar "destruir-datos" $(( $(date +%s) - inicio ))
else
  echo "== Paso 0: semana19-datos no existe"
fi
ESTADO_BASE="$(aws cloudformation describe-stacks --stack-name semana19-base --region "$REGION" --profile "$PERFIL_ADMIN" \
  --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo NO_EXISTE)"
# Paso 0b: the guardrail stack (activity 5) imports the base key, so it goes before the base.
if existe_stack semana19-ia; then
  echo "== Paso 0b: cdk destroy semana19-ia (Guardrail y prompts, actividad 5) antes que la red"
  cdk destroy semana19-ia --force --app "$PYTHON_CDK $APP" --profile "$PERFIL_DESPLIEGUE" --region "$REGION"
else
  echo "== Paso 0b: semana19-ia no existe"
fi

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
