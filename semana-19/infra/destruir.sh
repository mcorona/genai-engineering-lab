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
# English names: destroy.sh runs this script, and each flag above also takes its English name: --yes, --inventory,
# --all and --activity7-only.
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
PYTHON_BOTO="${S19_PYTHON_BOTO:-$RAIZ/.venv/bin/python}"  # boto3: the inventory and the emptying (venv-cdk does not have it)
APP="$RAIZ/semana-19/infra/cdk/app.py"
REGISTRO="$RAIZ/semana-19/resultados/tiempos_despliegue.jsonl"
REGION="us-east-1"
MODO="simulacion"
TODO=0
SOLO_A7=0

for argumento in "$@"; do
  case "$argumento" in
    --si|--yes) MODO="si" ;;
    --inventario|--inventory) MODO="inventario" ;;
    --todo|--all) TODO=1 ;;
    --solo-actividad7|--activity7-only) SOLO_A7=1 ;;
    *) echo "unrecognized argument: $argumento" >&2; exit 2 ;;
  esac
done
if [[ "$TODO" == "1" && "$MODO" != "si" ]]; then
  echo "--todo (--all) only works with --si (--yes)." >&2
  exit 2
fi
if [[ "$SOLO_A7" == "1" && "$TODO" == "1" ]]; then
  echo "--solo-actividad7 and --todo cannot be combined." >&2
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
  echo "== Simulation. No AWS calls were made."
  echo "00a) cdk destroy semana19-agentes-comparacion  (activity 7, disposable: first)"
  echo "00b) cdk destroy semana19-gateway              (activity 7: gateway, target, policies and engine)"
  if [[ "$SOLO_A7" == "1" ]]; then
    echo "00z) inventory of the activity 7 categories (they must be empty); the rest stays"
    exit 0
  fi
  echo "00c1) empty the judge's bucket and delete its jobs  (vaciar_eval.py --si, admin profile; activity 8)"
  echo "00c2) cdk destroy semana19-eval              (activity 8: the judge's bucket and role)"
  echo "00c) cdk destroy semana19-computo              (activity 6: agent, API, approval, users)"
  echo "0a) empty the KB documents bucket  (vaciar_datos.py --si, admin profile; versioned, activity 8)"
  echo "0) semana19-datos: cdk destroy          (PostgreSQL database and KB, before the network)"
  echo "0b) cdk destroy semana19-ia              (Guardrail and prompts; before the network because it imports the key)"
  echo "1) cdk destroy semana19-base            (deployment profile; deleting is still allowed under the freeze)"
  echo "2) empty the bootstrap bucket and ECR  (vaciar_bootstrap.py --si, admin profile)"
  echo "3) aws cloudformation delete-stack semana19-cdktoolkit  (admin profile; schedules the deletion of the bootstrap key)"
  if [[ "$TODO" == "1" ]]; then
    echo "4) aws cloudformation delete-stack semana19-control  (admin profile; one retry if only the permissions boundary failed)"
  else
    echo "4) semana19-control stays (--todo was not passed)"
  fi
  echo "4c) delete the implicit Lambda log groups /aws/lambda/semana19-*  (admin profile; activity 8)"
  echo "5) inventory (read-only): only what inventario.py::permitidos lists is allowed"
  echo "For the inventory without deleting anything: destruir.sh --inventario. To act: destruir.sh --si, with your OK."
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
    echo "== $paso: $pila does not exist"
  fi
}

destruir_pila_computo semana19-agentes-comparacion "Step 00a"
destruir_pila_computo semana19-gateway "Step 00b"
if [[ "$SOLO_A7" == "1" ]]; then
  echo "== Step 00z: activity 7 inventory (read-only)"
  "$PYTHON_BOTO" "$RAIZ/semana-19/infra/inventario.py" --perfil "$PERFIL_LECTURA" --region "$REGION" --solo-actividad7
  exit $?
fi
echo "== Step 00c1: empty the judge's bucket and delete its evaluation jobs (activity 8)"
"$PYTHON_BOTO" "$RAIZ/semana-19/infra/vaciar_eval.py" --perfil "$PERFIL_ADMIN" --region "$REGION" --si
destruir_pila_computo semana19-eval "Step 00c2"
destruir_pila_computo semana19-computo "Step 00c"

if existe_stack semana19-datos; then
  # Activity 8: the documents bucket is versioned without auto-delete; CloudFormation cannot delete it with versions.
  echo "== Step 0a: empty the KB documents bucket (vaciar_datos.py --si, admin profile)"
  "$PYTHON_BOTO" "$RAIZ/semana-19/infra/vaciar_datos.py" --perfil "$PERFIL_ADMIN" --region "$REGION" --si
  inicio=$(date +%s)
  echo "== Step 0: cdk destroy semana19-datos (PostgreSQL database) before the network"
  cdk destroy semana19-datos --force --app "$PYTHON_CDK $APP" --profile "$PERFIL_DESPLIEGUE" --region "$REGION"
  registrar "destruir-datos" $(( $(date +%s) - inicio ))
else
  echo "== Step 0: semana19-datos does not exist"
fi
ESTADO_BASE="$(aws cloudformation describe-stacks --stack-name semana19-base --region "$REGION" --profile "$PERFIL_ADMIN" \
  --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo NO_EXISTE)"
# Step 0b: the guardrail stack (activity 5) imports the base key, so it goes before the base.
if existe_stack semana19-ia; then
  echo "== Step 0b: cdk destroy semana19-ia (Guardrail and prompts, activity 5) before the network"
  cdk destroy semana19-ia --force --app "$PYTHON_CDK $APP" --profile "$PERFIL_DESPLIEGUE" --region "$REGION"
else
  echo "== Step 0b: semana19-ia does not exist"
fi

# Known case (2026-11-13): the custom resource that restricts the default SG cannot be deleted, because its Lambda
# role has no Authorize* rights under the permissions boundary. It is an AWS-less CloudFormation resource: retaining
# it leaves nothing in the account. Only that resource is retained; the rest of the stack is deleted. Any other
# failed resource stops the script.
retener_sg_por_defecto() {
  local inicio retenidos
  inicio=$(date +%s)
  retenidos="$(aws cloudformation describe-stack-events --stack-name semana19-base --region "$REGION" --profile "$PERFIL_ADMIN" \
    --query "StackEvents[?ResourceStatus=='DELETE_FAILED' && ResourceType=='Custom::VpcRestrictDefaultSG'].LogicalResourceId" \
    --output text | tr '\t' '\n' | sort -u | paste -sd, -)"
  if [[ -z "$retenidos" ]]; then
    echo "The failed custom resource was not identified; review the stack events before going on." >&2
    exit 1
  fi
  aws cloudformation delete-stack --stack-name semana19-base --region "$REGION" --profile "$PERFIL_ADMIN" \
    --retain-resources "$retenidos"
  aws cloudformation wait stack-delete-complete --stack-name semana19-base --region "$REGION" --profile "$PERFIL_ADMIN"
  registrar "destruir-base-retenido" $(( $(date +%s) - inicio ))
}

if [[ "$ESTADO_BASE" == "DELETE_FAILED" ]]; then
  echo "== Step 1b: semana19-base in DELETE_FAILED: only the default SG custom resource is retained"
  retener_sg_por_defecto
elif [[ "$ESTADO_BASE" != "NO_EXISTE" ]]; then
  inicio=$(date +%s)
  echo "== Step 1: cdk destroy semana19-base"
  # Week 20 (2026-11-23): the first delete of a fresh base always ends in DELETE_FAILED on that custom resource, so
  # the script goes on to step 1b in the same run instead of stopping and needing a second one.
  if cdk destroy semana19-base --force --app "$PYTHON_CDK $APP" --profile "$PERFIL_DESPLIEGUE" --region "$REGION"; then
    registrar "destruir-base" $(( $(date +%s) - inicio ))
  else
    estado="$(aws cloudformation describe-stacks --stack-name semana19-base --region "$REGION" --profile "$PERFIL_ADMIN" \
      --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo NO_EXISTE)"
    if [[ "$estado" != "DELETE_FAILED" ]]; then
      echo "cdk destroy semana19-base failed and the stack is in $estado; review the events before going on." >&2
      exit 1
    fi
    echo "== Step 1b: semana19-base ended in DELETE_FAILED: only the default SG custom resource is retained"
    retener_sg_por_defecto
  fi
else
  echo "== Step 1: semana19-base does not exist"
fi

if existe_stack semana19-cdktoolkit; then
  echo "== Step 2: empty the bootstrap bucket and ECR"
  "$PYTHON_BOTO" "$RAIZ/semana-19/infra/vaciar_bootstrap.py" --perfil "$PERFIL_ADMIN" --region "$REGION" --si
  inicio=$(date +%s)
  echo "== Step 3: delete semana19-cdktoolkit (schedules the deletion of its KMS key)"
  aws cloudformation delete-stack --stack-name semana19-cdktoolkit --region "$REGION" --profile "$PERFIL_ADMIN"
  aws cloudformation wait stack-delete-complete --stack-name semana19-cdktoolkit --region "$REGION" --profile "$PERFIL_ADMIN"
  registrar "destruir-bootstrap" $(( $(date +%s) - inicio ))
else
  echo "== Step 2-3: semana19-cdktoolkit does not exist"
fi

if [[ "$TODO" == "1" ]] && existe_stack semana19-control; then
  inicio=$(date +%s)
  echo "== Step 4: delete semana19-control"
  aws cloudformation delete-stack --stack-name semana19-control --region "$REGION" --profile "$PERFIL_ADMIN"
  if ! aws cloudformation wait stack-delete-complete --stack-name semana19-control --region "$REGION" --profile "$PERFIL_ADMIN"; then
    # Known case (2026-11-19): CloudFormation deleted the permissions boundary (semana19-limite) while the stack's own
    # roles that use it were still being deleted, and IAM answered 409. Once the roles are gone, one retry deletes it.
    # Only that resource may have failed; anything else stops here.
    fallidos="$(aws cloudformation describe-stack-resources --stack-name semana19-control --region "$REGION" \
      --profile "$PERFIL_ADMIN" --query "StackResources[?ResourceStatus=='DELETE_FAILED'].LogicalResourceId" --output text)"
    if [[ "$fallidos" != Limite* || "$fallidos" == *[[:space:]]* ]]; then
      echo "semana19-control in DELETE_FAILED because of: $fallidos; review the stack events before going on." >&2
      exit 1
    fi
    echo "== Step 4b: semana19-control failed only on the permissions boundary (a race with its roles): one retry"
    aws cloudformation delete-stack --stack-name semana19-control --region "$REGION" --profile "$PERFIL_ADMIN"
    aws cloudformation wait stack-delete-complete --stack-name semana19-control --region "$REGION" --profile "$PERFIL_ADMIN"
  fi
  registrar "destruir-control" $(( $(date +%s) - inicio ))
fi

# Activity 8: a Lambda without its own log group gets /aws/lambda/<function> from the runtime, outside CloudFormation
# (the datos loader, 2026-11-19). Once no stack of the project is left, those groups are deleted by name prefix.
echo "== Step 4c: delete the implicit Lambda log groups (/aws/lambda/semana19-*)"
for grupo in $(aws logs describe-log-groups --log-group-name-prefix /aws/lambda/semana19- --region "$REGION" \
    --profile "$PERFIL_ADMIN" --query "logGroups[].logGroupName" --output text); do
  aws logs delete-log-group --log-group-name "$grupo" --region "$REGION" --profile "$PERFIL_ADMIN"
  echo "deleted: $grupo"
done

echo "== Step 5: inventory (read-only)"
set +e
inventario
codigo=$?
set -e
if [[ "$codigo" -ne 0 ]]; then
  echo "The inventory found something outside the allowed list. Review 'inesperados' (unexpected) before calling it done." >&2
  exit "$codigo"
fi
echo "== Clean inventory: only what is allowed."
