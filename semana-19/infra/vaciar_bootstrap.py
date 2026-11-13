"""Week 19, activity 3: empties the bootstrap assets bucket (every version and delete marker) and deletes its ECR
repository, so CloudFormation can delete the semana19-cdktoolkit stack. Dry run by default: it only counts.

    python3 semana-19/infra/vaciar_bootstrap.py --perfil <admin>          # counts, read-only
    python3 semana-19/infra/vaciar_bootstrap.py --perfil <admin> --si     # deletes (destruir.sh calls it with --si)

The bucket and repository names contain the account ID, so they are never printed. Output shows counts only.
"""
from __future__ import annotations

import argparse
import json
import sys

STACK = "semana19-cdktoolkit"


def recursos(cfn) -> dict:
    salida = {"bucket": None, "ecr": None}
    for p in cfn.get_paginator("describe_stack_resources").paginate(StackName=STACK):
        for r in p["StackResources"]:
            if r["ResourceType"] == "AWS::S3::Bucket":
                salida["bucket"] = r["PhysicalResourceId"]  # the bootstrap stack has exactly one bucket
            if r["ResourceType"] == "AWS::ECR::Repository":
                salida["ecr"] = r["PhysicalResourceId"]
    return salida


def vaciar(s3, bucket: str, si: bool) -> dict:
    versiones = marcadores = 0
    for p in s3.get_paginator("list_object_versions").paginate(Bucket=bucket):
        objetos = [{"Key": v["Key"], "VersionId": v["VersionId"]} for v in p.get("Versions", [])]
        objetos += [{"Key": m["Key"], "VersionId": m["VersionId"]} for m in p.get("DeleteMarkers", [])]
        versiones += len(p.get("Versions", []))
        marcadores += len(p.get("DeleteMarkers", []))
        if si:
            for i in range(0, len(objetos), 1000):
                s3.delete_objects(Bucket=bucket, Delete={"Objects": objetos[i:i + 1000], "Quiet": True})
    return {"versiones": versiones, "marcadores_de_borrado": marcadores, "borrado": si}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--perfil", required=True)
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--si", action="store_true", help="borra (sin esta bandera solo cuenta)")
    a = ap.parse_args()
    import boto3
    sesion = boto3.Session(profile_name=a.perfil, region_name=a.region)
    cfn, s3, ecr = sesion.client("cloudformation"), sesion.client("s3"), sesion.client("ecr")
    r = recursos(cfn)
    informe = {"stack": STACK, "bucket_encontrado": bool(r["bucket"]), "ecr_encontrado": bool(r["ecr"])}
    if r["bucket"]:
        informe["bucket"] = vaciar(s3, r["bucket"], a.si)
    if r["ecr"]:
        imagenes = sum(len(p["imageIds"]) for p in ecr.get_paginator("list_images").paginate(
            repositoryName=r["ecr"]))
        informe["ecr"] = {"imagenes": imagenes, "borrado": a.si}
        if a.si:
            ecr.delete_repository(repositoryName=r["ecr"], force=True)
    print(json.dumps(informe, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
