#!/usr/bin/env bash
# Week 12 (AWS): deletes everything the week creates, in dependency order. An administrator runs it.
#   ./aws_borrar.sh                         shows what it would delete (a dry run, the default)
#   ./aws_borrar.sh --confirmar             deletes the KBs, data sources, vector bucket, document bucket and roles
#   ./aws_borrar.sh --confirmar --presupuesto   also deletes the budget (only after reviewing the invoice)
#   English names: --confirm = --confirmar, --budget = --presupuesto; aws_delete.sh = this script.
# It only touches resources with the semana12 prefix; it does not touch other buckets or budgets in the account.
set -uo pipefail
cd "$(dirname "$0")"; source config.sh
export AWS_PAGER=""
HAZ=0; PRES=0; for a in "$@"; do case "$a" in --confirmar|--confirm) HAZ=1 ;; --presupuesto|--budget) PRES=1 ;; esac; done
run() { if [ $HAZ -eq 1 ]; then echo "+ $*"; "$@" >/dev/null || echo "  (failed: $*)"; else echo "[dry run] $*"; fi; }
R="--region $REGION"

# 1. Knowledge Bases with the prefix and their data sources. Each data source is first switched to dataDeletionPolicy RETAIN, so the KB
#    does not try to delete its vectors (they go with the vector bucket in step 2). Without this, the KB ends in DELETE_UNSUCCESSFUL
#    if the index or the role disappears before it finishes. Indexes and roles are deleted only when no KB is left.
retener() {
  local f; f=$(mktemp)
  aws bedrock-agent get-data-source $R --knowledge-base-id $1 --data-source-id $2 --output json | python3 -c '
import json, sys
d = json.load(sys.stdin)["dataSource"]
campos = ("knowledgeBaseId", "dataSourceId", "name", "description", "dataSourceConfiguration",
          "vectorIngestionConfiguration", "serverSideEncryptionConfiguration")
o = {k: d[k] for k in campos if k in d}
o["dataDeletionPolicy"] = "RETAIN"
print(json.dumps(o))' > $f
  run aws bedrock-agent update-data-source $R --cli-input-json file://$f
  rm -f $f
}
kbs() { aws bedrock-agent list-knowledge-bases $R --query "knowledgeBaseSummaries[?starts_with(name,'$PREFIJO')].$1" --output text; }
for kb in $(kbs knowledgeBaseId); do
  for ds in $(aws bedrock-agent list-data-sources $R --knowledge-base-id $kb --query 'dataSourceSummaries[].dataSourceId' --output text); do
    retener $kb $ds
    run aws bedrock-agent delete-data-source $R --knowledge-base-id $kb --data-source-id $ds
  done
  run aws bedrock-agent delete-knowledge-base $R --knowledge-base-id $kb
done
if [ $HAZ -eq 1 ]; then
  for i in $(seq 1 30); do
    sleep 10; EST=$(kbs status)
    [ -z "$EST" ] && { echo "Knowledge Bases: deleted"; break; }
    if echo "$EST" | grep -q DELETE_UNSUCCESSFUL; then
      echo "Knowledge Bases in DELETE_UNSUCCESSFUL; indexes and roles are not deleted yet:"
      for kb in $(kbs knowledgeBaseId); do
        echo "  $kb: $(aws bedrock-agent get-knowledge-base $R --knowledge-base-id $kb --query 'knowledgeBase.[status,failureReasons]' --output text)"
      done
      exit 1
    fi
    echo "  waiting for the Knowledge Bases to be deleted ($EST)"
  done
  [ -n "$(kbs status)" ] && { echo "The Knowledge Bases did not finish deleting in 5 min; run the script again."; exit 1; }
fi

# 2. Vector buckets with the prefix: indexes and bucket.
for vb in $(aws s3vectors list-vector-buckets $R --query "vectorBuckets[?starts_with(vectorBucketName,'$PREFIJO')].vectorBucketName" --output text); do
  for ix in $(aws s3vectors list-indexes $R --vector-bucket-name $vb --query 'indexes[].indexName' --output text); do
    run aws s3vectors delete-index $R --vector-bucket-name $vb --index-name $ix
  done
  run aws s3vectors delete-vector-bucket $R --vector-bucket-name $vb
done

# 3. S3 buckets with the prefix: empty and delete.
for b in $(aws s3api list-buckets --query "Buckets[?starts_with(Name,'$PREFIJO')].Name" --output text); do
  run aws s3 rm s3://$b --recursive
  run aws s3api delete-bucket --bucket $b $R
done

# 4. Roles with the prefix (inline policies first).
for rol in $(aws iam list-roles --query "Roles[?starts_with(RoleName,'$PREFIJO')].RoleName" --output text); do
  for pol in $(aws iam list-role-policies --role-name $rol --query 'PolicyNames' --output text); do
    run aws iam delete-role-policy --role-name $rol --policy-name $pol
  done
  run aws iam delete-role --role-name $rol
done
[ $HAZ -eq 1 ] && { aws configure set profile.$PERFIL_AWS.role_arn ""; echo "profile $PERFIL_AWS: role_arn cleared"; }

# 5. GitHub's OIDC provider (activity 9), only if week 12 created it (tag proyecto=semana12).
for prov in $(aws iam list-open-id-connect-providers --query "OpenIDConnectProviderList[?contains(Arn,'token.actions.githubusercontent.com')].Arn" --output text); do
  if aws iam list-open-id-connect-provider-tags --open-id-connect-provider-arn $prov --query "Tags[?Key=='$ETIQUETA_CLAVE' && Value=='$ETIQUETA_VALOR']" --output text | grep -q .; then
    run aws iam delete-open-id-connect-provider --open-id-connect-provider-arn $prov
  fi
done

# 6. The budget, only if requested.
if [ $PRES -eq 1 ]; then run aws budgets delete-budget --account-id "$CUENTA_AWS" --budget-name "$PREFIJO"; fi
echo; ./inventario.sh aws
