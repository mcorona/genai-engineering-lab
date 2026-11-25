"""Week 19, activity 8: empties the knowledge base documents bucket before semana19-datos is destroyed.

The bucket (DocsKb in infra/cdk/app.py) is versioned and has no auto-delete, so CloudFormation cannot delete it while
any version is left: the teardown of 2026-11-19 ended with semana19-datos in DELETE_FAILED on that bucket (S3 409,
"You must delete all versions in the bucket"). Every version and delete marker is removed with the bootstrap's own
`vaciar` (infra/vaciar_bootstrap.py); the stack then deletes the empty bucket. Dry run by default: it only counts.

    python3 semana-19/infra/vaciar_datos.py --perfil <admin>          # counts, read-only
    python3 semana-19/infra/vaciar_datos.py --perfil <admin> --si     # deletes (destruir.sh calls it with --si)

The bucket name contains the account ID, so it is never printed. Output shows counts only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

STACK = "semana19-datos"
PREFIJO_LOGICO = "DocsKb"   # the logical id CDK derives from the construct id "DocsKb"

_spec = importlib.util.spec_from_file_location("vaciar_bootstrap", Path(__file__).resolve().parent / "vaciar_bootstrap.py")
_bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
vaciar = _bootstrap.vaciar


def bucket_de_documentos(cfn) -> str | None:
    """The documents bucket of the datos stack, or None when the stack or the bucket is already gone."""
    try:
        recursos = cfn.describe_stack_resources(StackName=STACK)["StackResources"]
    except Exception as error:  # noqa: BLE001 - a stack that does not exist has nothing to empty
        if "does not exist" in str(error):
            return None
        raise
    buckets = [r["PhysicalResourceId"] for r in recursos if r["ResourceType"] == "AWS::S3::Bucket"
               and r["LogicalResourceId"].startswith(PREFIJO_LOGICO) and r["ResourceStatus"] != "DELETE_COMPLETE"
               and r.get("PhysicalResourceId")]
    if len(buckets) > 1:
        raise RuntimeError(f"{len(buckets)} buckets {PREFIJO_LOGICO}* in {STACK}: expected one")
    return buckets[0] if buckets else None


def main() -> int:  # pragma: no cover - live only
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--perfil", "--profile", required=True, metavar="PROFILE")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--si", "--yes", action="store_true", help="deletes (without this flag it only counts)")
    a = ap.parse_args()
    import boto3
    sesion = boto3.Session(profile_name=a.perfil, region_name=a.region)
    bucket = bucket_de_documentos(sesion.client("cloudformation"))
    informe = {"stack": STACK, "bucket_encontrado": bool(bucket)}
    if bucket:
        informe["bucket"] = vaciar(sesion.client("s3"), bucket, a.si)
    print(json.dumps(informe, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
