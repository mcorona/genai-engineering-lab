"""Week 19, activity 8: Bedrock model evaluation over the deployed agent's answers (LLM as a judge, BYOIR).

Bring your own inference responses: the agent already answered in eval_aws.py, and the job only judges. The dataset
is one JSON line per task of the main run (not the warm-up). The keys are the documented ones
(bedrock/latest/userguide/model-evaluation-prompt-datasets-judge.html):
- `prompt`: the task message the agent received, plus the tool results it saw (its SQL and up to 20 rows each).
  Builtin.Faithfulness is judged against the prompt, and the dataset has no separate context field;
- `referenceResponse`: the expected rows recomputed on RDS (eval_aws.py, loader `esperados` mode);
- `category`: the task id. The output repeats the input record, so each result is matched back by this id;
- `modelResponses`: one response, with the single `modelIdentifier` the job allows.
At most 1000 prompts per job (the same page); here there are 20.

Metrics: Builtin.Correctness, Builtin.Completeness and Builtin.Faithfulness. The judge is ia/config.py's
MODELO_JUEZ_ID (Amazon Nova Pro through its US profile), a model different from the evaluated one (MODELO_ID, Claude
Haiku 4.5). The verdict thresholds are fixed in comparar_jueces.py.

The job runs with the service role and bucket of the stack semana19-eval: SSE-KMS with the base key, public access
blocked, TLS only, objects expire in 7 days. The role trusts bedrock.amazonaws.com for this account's evaluation jobs
only. The job itself takes no customer key: the data at rest is the bucket's, encrypted with the base key, and the
base key's policy needs no change. Once the results are downloaded (and saved redacted in the repo), the script
deletes its input and output objects, so the bucket is empty for the destroy.

Cap: before the job is created, the judge's tokens are estimated from the dataset (characters/4, times the metrics,
plus the judge's own instructions and an output allowance). If the estimate in USD at Nova Pro's price exceeds
TOPE_USD, no job is created and the step is reported as aborted. The real charge comes from Cost Explorer (step 4).

Simulation by default (builds and checks the dataset, prints the estimate); `--si` uploads, creates, waits and
downloads. Run by Manuel with the admin profile:

    S19_PERFIL=manuel-admin .venv/bin/python semana-19/eval/juez_bedrock.py --si
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
if str(S19) not in sys.path:
    sys.path.insert(0, str(S19))

from agentes import comparar as C  # noqa: E402
from comun.redaccion import redactar  # noqa: E402
from ia.config import MODELO_JUEZ_ID as MODELO_JUEZ  # noqa: E402

REGION = "us-east-1"
# Price List API, AmazonBedrock, Amazon Nova Pro on demand, us-east-1, read in step 1 of activity 8 (2026-11-19).
PRECIO_JUEZ_USD_POR_1K = {"entrada": 0.0008, "salida": 0.0032}
METRICAS = ("Builtin.Correctness", "Builtin.Completeness", "Builtin.Faithfulness")
ID_RESPUESTAS = "semana19-agente"
TIPO_DE_TAREA = "QuestionAndAnswer"   # the EvaluationTaskType values in botocore 1.43.122's bedrock model
TOPE_USD = 0.45
MAX_PROMPTS = 1000
LARGO_PROMPT = 12_000
INSTRUCCIONES_DEL_JUEZ_TOKENS = 1_500   # allowance per metric for the judge's built-in prompt (not published)
SALIDA_DEL_JUEZ_TOKENS = 400            # allowance per metric for the judge's rating and explanation
SALIDA = S19 / "resultados" / "eval_aws"
ARCHIVO = "juez_bedrock.json"
CLAVES = {"prompt", "referenceResponse", "category", "modelResponses"}


# ---------------------------------------------------------------- the dataset

def _filas_texto(filas) -> str:
    return json.dumps(filas, ensure_ascii=False, default=str)


def prompt_de(tarea: dict, contexto: list[dict]) -> str:
    """The task message plus what the tools returned, as the agent saw it."""
    partes = [C.texto_de_la_tarea(tarea), "", "Resultados de las herramientas:"]
    if not contexto:
        partes.append("(ninguno)")
    for i, c in enumerate(contexto, 1):
        partes.append(f"[{i}] SQL: {c.get('sql')}")
        partes.append(f"[{i}] error: {c['error']}" if c.get("error") else f"[{i}] filas: {_filas_texto(c.get('filas'))}")
    texto = "\n".join(partes)
    return texto if len(texto) <= LARGO_PROMPT else texto[:LARGO_PROMPT - 12] + "\n[recortado]"


REFERENCIA_SIN_FILAS = {
    "requiere_aclaracion": "La respuesta correcta pide una aclaración y no inventa un criterio. Motivo: {motivo}",
    "abstenida": "La respuesta correcta se abstiene: los datos no permiten contestar. Motivo: {motivo}",
}


def referencia_de(tarea: dict, esperados: dict[str, list]) -> str:
    """The expected rows per output key; for the tasks with no rows (ambiguous or unanswerable, week 13's
    estado_esperado), the expected behaviour and week 13's reason."""
    if tarea["estado_esperado"] in REFERENCIA_SIN_FILAS:
        return REFERENCIA_SIN_FILAS[tarea["estado_esperado"]].format(motivo=tarea.get("motivo", ""))
    claves = sorted(k for k in esperados if k.split("/", 1)[0] == tarea["id"])
    if sorted(k.split("/", 1)[1] for k in claves) != sorted(tarea["salida"]):
        raise ValueError(f"{tarea['id']}: faltan filas esperadas")
    return "\n".join(f"{k.split('/', 1)[1]}: {_filas_texto(esperados[k])}" for k in claves)


def linea(tarea: dict, fila: dict, esperados: dict[str, list]) -> dict:
    return {"prompt": prompt_de(tarea, fila.get("contexto") or []),
            "referenceResponse": referencia_de(tarea, esperados),
            "category": tarea["id"],
            "modelResponses": [{"response": fila.get("respuesta") or "", "modelIdentifier": ID_RESPUESTAS}]}


def construir(tareas: list[dict], crudo: dict, cuentas=()) -> list[dict]:
    """One line per main-run task that ran (an aborted task has no answer to judge). Redacted before upload."""
    por_id = {t["id"]: t for t in tareas}
    lineas = [linea(por_id[f["id_tarea"]], f, crudo["esperados"]) for f in crudo["filas"] if f.get("estado") != "no_corrida"]
    return [redactar(l, cuentas) for l in lineas]


def validar(lineas: list[dict]) -> list[str]:
    """The documented schema. Returns the problems (empty: valid)."""
    errores = []
    if not 1 <= len(lineas) <= MAX_PROMPTS:
        errores.append(f"{len(lineas)} prompts: deben ser de 1 a {MAX_PROMPTS}")
    ids = set()
    for i, l in enumerate(lineas):
        if not set(l) <= CLAVES or "prompt" not in l or "modelResponses" not in l:
            errores.append(f"línea {i}: claves {sorted(l)}")
            continue
        if not isinstance(l["prompt"], str) or not l["prompt"]:
            errores.append(f"línea {i}: prompt vacío")
        r = l["modelResponses"]
        if not (isinstance(r, list) and len(r) == 1 and set(r[0]) == {"response", "modelIdentifier"}):
            errores.append(f"línea {i}: modelResponses debe traer una sola respuesta")
        else:
            ids.add(r[0]["modelIdentifier"])
        if l.get("category") in {x.get("category") for x in lineas[:i]}:
            errores.append(f"línea {i}: category repetida")
    if len(ids) > 1:
        errores.append(f"un solo modelIdentifier por trabajo; hay {sorted(ids)}")
    return errores


def jsonl(lineas: list[dict]) -> str:
    return "".join(json.dumps(l, ensure_ascii=False, sort_keys=True) + "\n" for l in lineas)


# ---------------------------------------------------------------- the cap

def estimar(lineas: list[dict]) -> dict:
    entrada = sum(math.ceil(len(json.dumps(l, ensure_ascii=False)) / 4) + INSTRUCCIONES_DEL_JUEZ_TOKENS for l in lineas) * len(METRICAS)
    salida = SALIDA_DEL_JUEZ_TOKENS * len(lineas) * len(METRICAS)
    usd = entrada / 1000 * PRECIO_JUEZ_USD_POR_1K["entrada"] + salida / 1000 * PRECIO_JUEZ_USD_POR_1K["salida"]
    return {"tokens_entrada": entrada, "tokens_salida": salida, "usd": round(usd, 6), "tope_usd": TOPE_USD,
            "cabe": usd <= TOPE_USD}


# ---------------------------------------------------------------- the job

def nombre_del_trabajo(ahora: float) -> str:
    return time.strftime("semana19-juez-%Y%m%d-%H%M%S", time.gmtime(ahora))


def solicitud(nombre: str, *, rol: str, bucket: str) -> dict:
    """CreateEvaluationJob's parameters (shape from botocore's bedrock model)."""
    return {
        "jobName": nombre, "roleArn": rol, "applicationType": "ModelEvaluation",
        "jobDescription": "Week 19, activity 8: judge over the deployed agent's answers (BYOIR).",
        "jobTags": [{"key": "proyecto", "value": "semana19"}],
        "evaluationConfig": {"automated": {
            "datasetMetricConfigs": [{"taskType": TIPO_DE_TAREA, "metricNames": list(METRICAS), "dataset": {
                "name": "golden-ci-20", "datasetLocation": {"s3Uri": f"s3://{bucket}/entrada/{nombre}.jsonl"}}}],
            "evaluatorModelConfig": {"bedrockEvaluatorModels": [{"modelIdentifier": MODELO_JUEZ}]}}},
        "inferenceConfig": {"models": [{"precomputedInferenceSource": {"inferenceSourceIdentifier": ID_RESPUESTAS}}]},
        "outputDataConfig": {"s3Uri": f"s3://{bucket}/salida/"},
    }


# ---------------------------------------------------------------- the results

def _explicacion(puntaje: dict) -> str | None:
    for d in puntaje.get("evaluatorDetails") or []:
        if d.get("explanation"):
            return d["explanation"]
    return puntaje.get("explanation")


def leer_resultados(registros: list[dict]) -> dict:
    """Output records -> {task id: {"puntajes": {metric: score}, "explicacion"}}. Matched by inputRecord.category.
    The judge output's layout is not on a page we could read (2026-11-19); the known keys come from the automatic
    jobs' output (model-evaluation-report-s3.html): automatedEvaluationResult.scores[].metricName/result and
    inputRecord. Anything else fails loudly here, so the format is checked on the real output, not assumed."""
    por_tarea: dict[str, dict] = {}
    for r in registros:
        entrada = r.get("inputRecord") or {}
        id_ = entrada.get("category")
        if not id_:
            raise ValueError(f"registro sin inputRecord.category: claves {sorted(r)}")
        puntajes, explicaciones = {}, []
        for p in (r.get("automatedEvaluationResult") or {}).get("scores") or []:
            nombre = p["metricName"] if p["metricName"].startswith("Builtin.") else f"Builtin.{p['metricName']}"
            valor = p.get("result")
            if valor is not None and not 0 <= float(valor) <= 1:
                raise ValueError(f"{id_} {nombre}: puntaje {valor} fuera de [0, 1]")
            puntajes[nombre] = None if valor is None else float(valor)
            if _explicacion(p):
                explicaciones.append(f"{nombre}: {_explicacion(p)}")
        if id_ in por_tarea:
            raise ValueError(f"{id_}: dos registros")
        por_tarea[id_] = {"puntajes": puntajes, "respuesta": ((entrada.get("modelResponses") or [{}])[0]).get("response"),
                          "explicacion": "\n".join(explicaciones) or None}
    return por_tarea


class AwsJuez:  # pragma: no cover - live only
    def __init__(self, perfil: str):
        import boto3
        self.s = boto3.Session(profile_name=perfil, region_name=REGION)
        self.cuenta = self.s.client("sts").get_caller_identity()["Account"]
        cfn = self.s.client("cloudformation")
        salidas = {o["OutputKey"]: o["OutputValue"] for o in cfn.describe_stacks(StackName="semana19-eval")["Stacks"][0]["Outputs"]}
        self.bucket, self.rol, self.llave = salidas["BucketJuez"], salidas["ArnRolJuez"], salidas["ArnLlave"]
        self.s3, self.bedrock = self.s.client("s3"), self.s.client("bedrock")

    def subir(self, clave: str, cuerpo: str):
        self.s3.put_object(Bucket=self.bucket, Key=clave, Body=cuerpo.encode("utf-8"), ServerSideEncryption="aws:kms",
                           SSEKMSKeyId=self.llave, ContentType="application/jsonl")

    def crear(self, params: dict) -> str:
        return self.bedrock.create_evaluation_job(**params)["jobArn"]

    def esperar(self, arn: str, dormir=time.sleep, maximo_s=3 * 3600) -> dict:
        inicio = time.time()
        while True:
            j = self.bedrock.get_evaluation_job(jobIdentifier=arn)
            if j["status"] not in ("InProgress", "Stopping"):
                return j
            if time.time() - inicio > maximo_s:
                self.bedrock.stop_evaluation_job(jobIdentifier=arn)
                raise SystemExit("el trabajo del juez pasó de 3 h; se pidió detenerlo")
            dormir(60)

    def borrar(self, nombre: str) -> int:
        """The job's input and output objects (the bucket is not versioned: a delete removes them)."""
        claves = [o["Key"] for prefijo in (f"entrada/{nombre}", f"salida/{nombre}/")
                  for p in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefijo)
                  for o in p.get("Contents", [])]
        for i in range(0, len(claves), 1000):
            self.s3.delete_objects(Bucket=self.bucket, Delete={"Objects": [{"Key": k} for k in claves[i:i + 1000]]})
        return len(claves)

    def resultados(self, nombre: str) -> list[dict]:
        registros = []
        for pagina in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=f"salida/{nombre}/"):
            for o in pagina.get("Contents", []):
                if o["Key"].endswith(".jsonl"):
                    texto = self.s3.get_object(Bucket=self.bucket, Key=o["Key"])["Body"].read().decode("utf-8")
                    registros += [json.loads(l) for l in texto.splitlines() if l.strip()]
        return registros


def _cargar_eval():
    import importlib.util
    spec = importlib.util.spec_from_file_location("eval_aws_para_juez", S19 / "eval" / "eval_aws.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main(argv=None) -> int:  # pragma: no cover - the CLI around the tested functions
    import os
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--si", action="store_true", help="actuar (por omisión solo simula)")
    a = ap.parse_args(argv)
    E = _cargar_eval()
    crudo_archivo = SALIDA / E.CRUDO
    if not crudo_archivo.exists():
        print(json.dumps({"simulacion": True, "metricas": METRICAS, "juez": MODELO_JUEZ, "tope_usd": TOPE_USD,
                          "falta": f"resultados/eval_aws/{E.CRUDO} (eval_aws.py --si)"}, ensure_ascii=False, indent=2))
        print("Simulación: no se llamó a AWS. Agrega --si para actuar.")
        return 0
    crudo = json.loads(crudo_archivo.read_text(encoding="utf-8"))
    lineas = construir(E.tareas_ci(), crudo)
    errores = validar(lineas)
    est = estimar(lineas)
    print(json.dumps({"prompts": len(lineas), "errores": errores, "estimacion": est}, ensure_ascii=False, indent=2))
    if errores:
        return 1
    if not est["cabe"]:
        resultado = {"estado": "abortado", "motivo": "tope_del_script", "estimacion": est}
        (SALIDA / ARCHIVO).write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("tope del juez rebasado en la estimación: no se crea el trabajo")
        return 1
    if not a.si:
        print("Simulación: no se llamó a AWS. Agrega --si para actuar.")
        return 0
    aws = AwsJuez(os.environ.get("S19_PERFIL", "manuel-admin"))
    nombre = nombre_del_trabajo(time.time())
    aws.subir(f"entrada/{nombre}.jsonl", jsonl(redactar(lineas, [aws.cuenta])))
    inicio = time.time()
    arn = aws.crear(solicitud(nombre, rol=aws.rol, bucket=aws.bucket))
    final = aws.esperar(arn)
    registros = aws.resultados(nombre) if final["status"] == "Completed" else []
    resultado = {"fecha": time.strftime("%Y-%m-%d"), "trabajo": nombre, "estado": final["status"],
                 "fallas": final.get("failureMessages"), "duracion_s": round(time.time() - inicio),
                 "juez": MODELO_JUEZ, "metricas": METRICAS, "estimacion": est,
                 "por_tarea": leer_resultados(registros) if registros else {}}
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / ARCHIVO).write_text(json.dumps(redactar(resultado, [aws.cuenta]), ensure_ascii=False, indent=2,
                                             sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(SALIDA / ARCHIVO, final["status"], len(resultado["por_tarea"]), "tareas juzgadas")
    print("objetos borrados del bucket del juez:", aws.borrar(nombre))
    return 0 if final["status"] == "Completed" and len(resultado["por_tarea"]) == len(lineas) else 1


if __name__ == "__main__":
    raise SystemExit(main())
