"""Week 19, activity 8: before semana19-eval is destroyed, empties the judge's bucket and deletes the judge's jobs.

juez_bedrock.py already deletes its objects after a good run; this covers a run that stopped halfway. The evaluation
jobs are not CloudFormation resources: the ones named semana19-juez-* that have ended are deleted with
BatchDeleteEvaluationJob, so the inventory finds none. A job still running is stopped first and reported.
Dry run by default: it only counts.

    python3 semana-19/infra/vaciar_eval.py --perfil <admin>          # counts, read-only
    python3 semana-19/infra/vaciar_eval.py --perfil <admin> --si     # deletes (destruir.sh calls it with --si)

Output shows counts and job states only (the bucket name and the job ARNs contain the account ID).
"""
from __future__ import annotations

import argparse
import json
import sys

STACK = "semana19-eval"
PREFIJO_TRABAJOS = "semana19-juez-"
# ListEvaluationJobs' nameContains must match [a-z0-9](-*[a-z0-9]){0,62}: no trailing hyphen (ValidationException in
# the teardown of 2026-11-19). The service filters by the stem; the exact prefix is checked here.
FILTRO_NOMBRE = PREFIJO_TRABAJOS.rstrip("-")
TERMINADOS = ("Completed", "Failed", "Stopped")


def bucket_del_stack(cfn) -> str | None:
    try:
        recursos = cfn.describe_stack_resources(StackName=STACK)["StackResources"]
    except Exception as error:  # noqa: BLE001 - a stack that does not exist has nothing to empty
        if "does not exist" in str(error):
            return None
        raise
    (bucket,) = [r["PhysicalResourceId"] for r in recursos if r["ResourceType"] == "AWS::S3::Bucket"] or [None]
    return bucket


def vaciar(s3, bucket: str, si: bool) -> dict:
    """Versions and delete markers too, in case the bucket ever had versioning (it does not)."""
    n = 0
    for p in s3.get_paginator("list_object_versions").paginate(Bucket=bucket):
        objetos = [{"Key": v["Key"], "VersionId": v["VersionId"]} for v in p.get("Versions", []) + p.get("DeleteMarkers", [])]
        n += len(objetos)
        if si:
            for i in range(0, len(objetos), 1000):
                s3.delete_objects(Bucket=bucket, Delete={"Objects": objetos[i:i + 1000], "Quiet": True})
    return {"objetos": n, "borrado": si}


def trabajos(bedrock) -> list[dict]:
    salida = []
    for p in bedrock.get_paginator("list_evaluation_jobs").paginate(nameContains=FILTRO_NOMBRE):
        salida += [{"arn": j["jobArn"], "nombre": j["jobName"], "estado": j["status"]}
                   for j in p.get("jobSummaries", []) if j["jobName"].startswith(PREFIJO_TRABAJOS)]
    return salida


def borrar_trabajos(bedrock, lista: list[dict], si: bool) -> dict:
    activos = [j for j in lista if j["estado"] not in TERMINADOS]
    terminados = [j for j in lista if j["estado"] in TERMINADOS]
    informe = {"encontrados": len(lista), "por_estado": {}, "detenidos": 0, "borrados": 0, "errores": []}
    for j in lista:
        informe["por_estado"][j["estado"]] = informe["por_estado"].get(j["estado"], 0) + 1
    if not si:
        return informe
    for j in activos:
        if j["estado"] == "InProgress":
            bedrock.stop_evaluation_job(jobIdentifier=j["arn"])
            informe["detenidos"] += 1
    for i in range(0, len(terminados), 25):
        r = bedrock.batch_delete_evaluation_job(jobIdentifiers=[j["arn"] for j in terminados[i:i + 25]])
        informe["borrados"] += len(r.get("evaluationJobs", []))
        informe["errores"] += [e.get("code") for e in r.get("errors", [])]
    return informe


def main() -> int:  # pragma: no cover - live only
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--perfil", required=True)
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--si", action="store_true", help="borra (sin esta bandera solo cuenta)")
    a = ap.parse_args()
    import boto3
    sesion = boto3.Session(profile_name=a.perfil, region_name=a.region)
    bucket = bucket_del_stack(sesion.client("cloudformation"))
    informe = {"stack": STACK, "bucket_encontrado": bool(bucket)}
    if bucket:
        informe["bucket"] = vaciar(sesion.client("s3"), bucket, a.si)
    bedrock = sesion.client("bedrock")
    informe["trabajos"] = borrar_trabajos(bedrock, trabajos(bedrock), a.si)
    print(json.dumps(informe, indent=2, ensure_ascii=False))
    pendientes = informe["trabajos"]["detenidos"] + len(informe["trabajos"]["errores"])
    return 0 if not pendientes else 1


if __name__ == "__main__":
    sys.exit(main())
