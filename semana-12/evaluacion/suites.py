"""Week 12: the week 11 suites over any retrieval system, with the same gold set and the same generator.

Each option of the week (the in-house pipeline, Bedrock Knowledge Bases, Vertex AI Search) comes in as a retrieval
backend that returns, per question, the ranking [(source, content), ...] with the latency and cost of retrieving.
Everything else is shared and does not change between options:
- gold set: semana-11/datasets/eval_rag_{es,en}.jsonl (75 per language: 65 answerable, 10 unanswerable), a user of the alfa
  tenant with every role;
- retrieval suite (65 answerable per language): recall@1/3/5/10, MRR, nDCG@10 and AP@5 with exact relevance (a
  chunk of the reference document that contains the literal passage; week 11, activity 2), plus doc_recall@5 (the
  reference document is in the top 5), which does not depend on where each service cuts its chunks;
- generation suite over what was retrieved (the 150 questions): top 5 to the common generator (Haiku 5.5 medium, week 11's
  solo_documentos prompt), judge Haiku 5.5 low: accuracy (in-house judge), faithfulness and answer relevancy (RAGAS),
  citation precision and coverage, correct and false abstention, and attribution of each failure to retrieval or generation
  (week 11, activity 5);
- cost and latency per query of retrieval and of generation.
Cache per backend in resultados/<backend>_cache.json (resumes); summary in resultados/<backend>_resumen.json and detail in
resultados/<backend>_detalle.csv. Backends: propio; bedrock (--config, an activity 4 Knowledge Base, with --modo comun
(the common generator) or --modo rag (Bedrock RetrieveAndGenerate with Claude Haiku 4.5)); vertex (--config <data store>:<search>,
activity 5).
"""
import argparse
import asyncio
import csv
import datetime as dt
import json
import math
import os
import statistics
import sys
import time
import urllib.error
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REPO = RAIZ.parent
sys.path.insert(0, str(REPO / "semana-11" / "experimentos"))
import sensibilidad as sens  # noqa: E402  (the week 11 retrieval and generation suites and the week 10 assistant)

sg, sr, a = sens.sg, sens.sr, sens.a
RES = RAIZ / "resultados"
K_GEN = 5
P = a.PRECIOS[f"anthropic:{a.HAIKU}"]
MET_REC = ("recall@1", "recall@3", "recall@5", "recall@10", "mrr", "ndcg@10", "ap@5", "doc_recall@5")


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, math.ceil(q * len(v)) - 1))] if v else float("nan")


# ---------- retrieval backends ----------

def recuperar_propio(items, guardar_uno):
    """The in-house pipeline (weeks 8 to 11): bge-m3 in LM Studio, pgvector semana10.chunks with the tenant and role filter inside
    the query, top 20 and reranking with Haiku 5.5 (week 11's `adoptado` configuration)."""
    import psycopg
    with psycopg.connect(os.environ["NLQ_DSN"]) as c:
        n, tenants = c.execute("SELECT count(*), array_agg(DISTINCT tenant_id) FROM semana10.chunks").fetchone()
    if n != 68 or tenants != ["alfa"]:
        raise SystemExit(f"semana10.chunks has {n} chunks from {tenants}; 68 from alfa were expected (the week 10 index, act. 7)")
    local = {}
    sr.recuperar(items, local)
    for x in items:
        r = local[f"adoptado::{x['id']}::{x['lang']}"]
        guardar_uno(x, {"ranking": r["ranking"], "latencia_s": r["latencia_s"], "costo": r["costo"],
                        "rerank_fallo": r.get("rerank_fallo", False)})


FILTRO_ALFA = {"andAll": [{"equals": {"key": "tenant_id", "value": "alfa"}},
                          {"orAll": [{"listContains": {"key": "roles", "value": r}} for r in sorted(a.USUARIO["roles"])]}]}
PERFIL_RAG = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
PRECIO_HAIKU45 = {"in": 1.10, "out": 5.50}   # Bedrock us-east-1, regional profile (resultados/costos_fijos.md)
PRECIO_COHERE, PRECIO_S3V_CONSULTA = 0.10, 0.055 / 1000


def _aws(servicio):
    import boto3
    from botocore.config import Config
    # With credentials in the environment (aws configure export-credentials --profile semana12), botocore[crt] is not needed
    perfil = None if os.getenv("AWS_ACCESS_KEY_ID") else os.getenv("PERFIL_AWS", "semana12")
    return boto3.Session(profile_name=perfil, region_name="us-east-1").client(
        servicio, config=Config(retries={"max_attempts": 6, "mode": "adaptive"}))


def _kb(config):
    """The KB id: from infra/estado_aws.json (local) or, without that file (CI), by looking it up by the name semana12-<config>."""
    ruta = RAIZ / "infra" / "estado_aws.json"
    if ruta.exists():
        estado = json.loads(ruta.read_text(encoding="utf-8"))
        if estado.get(config, {}).get("ingesta") != "COMPLETE":
            raise SystemExit(f"The KB {config} has no complete ingestion in infra/estado_aws.json")
        return estado[config]["kb_id"]
    kbs = _aws("bedrock-agent").list_knowledge_bases(maxResults=100)["knowledgeBaseSummaries"]
    kb = [k for k in kbs if k["name"] == f"semana12-{config}" and k["status"] == "ACTIVE"]
    if not kb:
        raise SystemExit(f"There is no active KB semana12-{config}")
    return kb[0]["knowledgeBaseId"]


def recuperar_bedrock(items, guardar_uno, config):
    """Bedrock Knowledge Bases, Retrieve API: vector search in S3 Vectors (the only one it supports) with the tenant
    and role filter inside the query, top 20, no reranking. One query at a time (the latency of a single query). Estimated
    cost: the question's embedding (Cohere multilingual) plus the S3 Vectors query."""
    kb, cli = _kb(config), _aws("bedrock-agent-runtime")
    for x in items:
        t0 = time.perf_counter()
        r = cli.retrieve(knowledgeBaseId=kb, retrievalQuery={"text": x["question"]},
                         retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 20, "filter": FILTRO_ALFA}})
        lat = time.perf_counter() - t0
        res = r["retrievalResults"]
        guardar_uno(x, {"ranking": [[z.get("metadata", {}).get("source", ""), z.get("content", {}).get("text", "")] for z in res],
                        "latencia_s": round(lat, 4), "costo": len(x["question"]) / 4 * PRECIO_COHERE / 1e6 + PRECIO_S3V_CONSULTA,
                        "tenants": sorted({str(z.get("metadata", {}).get("tenant_id")) for z in res}),
                        "uris": [z.get("location", {}).get("s3Location", {}).get("uri", "") for z in res[:5]]})


def generar_rag(items, cache, guardar, config):
    """Bedrock RetrieveAndGenerate: retrieves the top 5 with the same filter and answers with Claude Haiku 4.5 and Bedrock's
    default template, as a client would use it. The API returns no tokens: the cost is estimated at 4 characters
    per token over the template (≈ 1,500 characters), the question, the 5 passages and the answer."""
    from concurrent.futures import ThreadPoolExecutor
    kb, cli = _kb(config), _aws("bedrock-agent-runtime")
    cuenta = _aws("sts").get_caller_identity()["Account"]
    modelo = f"arn:aws:bedrock:us-east-1:{cuenta}:inference-profile/{PERFIL_RAG}"

    def uno(x):
        k = f"gen::{x['id']}::{x['lang']}"
        if k in cache:
            return
        t0 = time.perf_counter()
        r = cli.retrieve_and_generate(input={"text": x["question"]}, retrieveAndGenerateConfiguration={
            "type": "KNOWLEDGE_BASE", "knowledgeBaseConfiguration": {"knowledgeBaseId": kb, "modelArn": modelo,
                "retrievalConfiguration": {"vectorSearchConfiguration": {"numberOfResults": K_GEN, "filter": FILTRO_ALFA}}}})
        lat = time.perf_counter() - t0
        citadas = []
        for c in r.get("citations", []):
            for ref in c.get("retrievedReferences", []):
                par = [ref.get("metadata", {}).get("source", ""), ref.get("content", {}).get("text", "")]
                if par not in citadas:
                    citadas.append(par)
        texto = r["output"]["text"]
        ctx_chars = sum(len(c) for _, c in cache[f"rec::{x['id']}::{x['lang']}"]["ranking"][:K_GEN])
        tin, tout = (1500 + len(x["question"]) + ctx_chars) / 4, len(texto) / 4
        cache[k] = {"respuesta": texto, "latencia_s": round(lat, 3), "citadas": citadas, "costo_estimado": True,
                    "costo": (tin * PRECIO_HAIKU45["in"] + tout * PRECIO_HAIKU45["out"]) / 1e6}
        guardar()
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(uno, items))


# ---------- Vertex AI Search ----------
VX_TOKEN = {"t": None, "hasta": 0}
PAQUETE = RAIZ / "ingesta" / "paquete"
FILTRO_VX = ('tenant_id: ANY("alfa") AND roles: ANY(' + ",".join(f'"{r}"' for r in sorted(a.USUARIO["roles"])) + ")")
PRECIO_RANKING = 1.0 / 1000   # Vertex AI Search Ranking API, per request (resultados/costos_fijos.md)


def _vx_conf():
    import re as _re
    cfg = (RAIZ / "infra" / "config.sh").read_text()
    pref = _re.search(r"^PREFIJO=(\S+)", cfg, _re.M).group(1)
    proy = _re.search(r"^GCP_PROYECTO=\$\{GCP_PROYECTO:-([^}]+)\}", cfg, _re.M).group(1)
    return proy, f"{pref}-operador@{proy}.iam.gserviceaccount.com"


def _vx(url, cuerpo):
    import subprocess
    import urllib.request
    proy, sa = _vx_conf()
    if time.time() > VX_TOKEN["hasta"]:
        # In CI (VX_SIN_IMPERSONAR=1), gcloud already acts as the workflow's service account (Workload Identity Federation).
        imp = [] if os.getenv("VX_SIN_IMPERSONAR") else [f"--impersonate-service-account={sa}"]
        VX_TOKEN["t"] = subprocess.run(["gcloud", "auth", "print-access-token", *imp],
                                       capture_output=True, text=True, check=True).stdout.strip()
        VX_TOKEN["hasta"] = time.time() + 2700
    for intento in range(5):
        req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), method="POST", headers={
            "Authorization": f"Bearer {VX_TOKEN['t']}", "Content-Type": "application/json", "x-goog-user-project": proy})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and intento < 4:
                time.sleep(2 ** (intento + 1))
                continue
            raise SystemExit(f"Vertex HTTP {e.code}: {e.read().decode()[:400]}")


def recuperar_vertex(items, guardar_uno, config):
    """Vertex AI Search, the search API of the data store's app, top 20 with the tenant and role filter in the query.
    config = <data store>:<search>, with search:
      hibrida   the service's default ranking (keywords + embeddings);
      vectorial a formula ranking with semantic_similarity_score only (it reorders the candidates the service retrieves);
      semantico the hybrid search reordered with the semantic ranker (Ranking API, semantic-ranker-default@latest).
    vx-adm returns the service's chunks (layout parser); vx-ctl returns documents = in-house chunks (the package's text)."""
    import urllib.error  # noqa: F401
    store, busqueda = config.split(":")
    ruta = RAIZ / "infra" / "estado_gcp.json"
    estado = (json.loads(ruta.read_text(encoding="utf-8"))[store] if ruta.exists()
              else {"engine": f"semana12-{store}-app"})  # in CI, the fixed name that vertex_crear.py creates
    proy, _ = _vx_conf()
    base = f"https://discoveryengine.googleapis.com/v1/projects/{proy}/locations/global"
    url = f"{base}/collections/default_collection/engines/{estado['engine']}/servingConfigs/default_search:search"
    for x in items:
        # A minimum relevance threshold and automatic query expansion: without them the service returns 0 to 3 results
        # (and none for many English questions about Spanish documents). The top 20 is requested, as for the other options.
        cuerpo = {"query": x["question"], "pageSize": 20, "filter": FILTRO_VX, "relevanceThreshold": "LOWEST",
                  "queryExpansionSpec": {"condition": "AUTO"},
                  "contentSearchSpec": {"searchResultMode": "CHUNKS" if store == "vx-adm" else "DOCUMENTS"}}
        if busqueda == "vectorial":
            cuerpo.update({"rankingExpressionBackend": "RANK_BY_FORMULA", "rankingExpression": "semantic_similarity_score"})
        t0 = time.perf_counter()
        r = _vx(url, cuerpo)
        ranking, tenants = [], set()
        for z in r.get("results", []):
            if "chunk" in z:
                uri = z["chunk"].get("documentMetadata", {}).get("uri", "")
                partes = uri.split("/")  # gs://<bucket>/vx-adm/administrado/<tenant>/<file>
                tenant, stem = partes[-2], Path(partes[-1]).stem.removesuffix("_p1")
                texto = z["chunk"].get("content", "")
            else:
                tenant, stem, n = z["document"]["id"].split("__")
                texto = (PAQUETE / "controlado" / "chunks" / tenant / f"{stem}__{n}.txt").read_text(encoding="utf-8")
            tenants.add(tenant)
            ranking.append([stem, texto])
        costo = 0.0
        if busqueda == "semantico" and ranking:
            rr = _vx(f"{base}/rankingConfigs/default_ranking_config:rank", {
                "model": "semantic-ranker-default@latest", "query": x["question"], "topN": len(ranking),
                "records": [{"id": str(i), "content": c[:6000]} for i, (_, c) in enumerate(ranking)]})
            ranking = [ranking[int(rec["id"])] for rec in rr.get("records", [])]
            costo = PRECIO_RANKING
        guardar_uno(x, {"ranking": ranking, "latencia_s": round(time.perf_counter() - t0, 4), "costo": costo,
                        "tenants": sorted(tenants), "n_resultados": len(ranking)})


BACKENDS = {"propio": recuperar_propio, "bedrock": recuperar_bedrock, "vertex": recuperar_vertex}


# ---------- metrics ----------

def metricas_recuperacion(x, ranking):
    # A service can return fewer than 10 results: the list is padded with empty (non-relevant) entries for the @k metrics.
    ranking = list(ranking) + [["", ""]] * max(0, 10 - len(ranking))
    m = sr.metricas([tuple(c) for c in ranking], x["gold"])
    fuentes = {Path(g["source"]).stem for g in x["gold"]}
    m["doc_recall@5"] = len(fuentes & {s for s, _ in ranking[:5]}) / len(fuentes)
    return {k: m[k] for k in MET_REC}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=sorted(BACKENDS), default="propio")
    ap.add_argument("--config", default="", help="bedrock: adm-pred, adm-fijo, adm-fijo-bda or ctl-chunks; "
                    "vertex: <vx-adm|vx-ctl>:<hibrida|vectorial|semantico>")
    ap.add_argument("--modo", choices=("comun", "rag"), default="comun", help="comun: the common generator; rag: RetrieveAndGenerate")
    ap.add_argument("--limite", type=int, default=0, help="N questions per language and type (smoke test)")
    args = ap.parse_args()
    items = sg.items_todos()
    if args.limite:
        items = [x for lang in ("es", "en") for resp in (True, False)
                 for x in [y for y in items if y["lang"] == lang and y["respondible"] == resp][:args.limite]]
    if args.backend != "propio" and not args.config:
        raise SystemExit("--config is required for the managed backends")
    base = args.backend + (f"_{args.config.replace(':', '_')}" if args.config else "")
    nombre = base + ("_rag" if args.modo == "rag" else "") + (f"_humo{args.limite}" if args.limite else "")
    ruta = RES / f"{nombre}_cache.json"
    cache = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    if args.modo == "rag":  # the same retrieval as the common mode, if it has already been measured
        previa = RES / f"{base}{f'_humo{args.limite}' if args.limite else ''}_cache.json"
        if previa.exists():
            cache.update({kk: v for kk, v in json.loads(previa.read_text(encoding="utf-8")).items()
                          if kk.startswith("rec::") and kk not in cache})

    def guardar():
        ruta.write_text(json.dumps(cache, ensure_ascii=False) + "\n", encoding="utf-8")

    def guardar_uno(x, r):
        cache[f"rec::{x['id']}::{x['lang']}"] = r
    t0 = time.time()
    faltan = [x for x in items if f"rec::{x['id']}::{x['lang']}" not in cache]
    if faltan:
        if args.backend == "propio":
            BACKENDS[args.backend](faltan, guardar_uno)
        else:
            BACKENDS[args.backend](faltan, guardar_uno, args.config)
        guardar()
    ctx = {f"{x['id']}::{x['lang']}": {"chunks": cache[f"rec::{x['id']}::{x['lang']}"]["ranking"][:K_GEN]} for x in items}
    if args.modo == "rag":
        generar_rag(items, cache, guardar, args.config)
    else:
        sg.generar(items, ctx, cache, guardar, sistema=sens.SIS_SOLO_DOCUMENTOS)
    uso = asyncio.run(sg.evaluar(items, ctx, cache, guardar))
    guardar()

    filas = []
    for x in items:
        k = f"{x['id']}::{x['lang']}"
        rec, gen = cache[f"rec::{k}"], cache[f"gen::{k}"]
        f = {"id": x["id"], "lang": x["lang"], "respondible": x["respondible"],
             "tipo": "sin_respuesta" if not x["respondible"] else ("no_textual" if x["tipo"].startswith("no_textual") else "base"),
             "lat_rec": rec["latencia_s"], "costo_rec": rec["costo"], "lat_gen": gen["latencia_s"], "costo_gen": gen["costo"],
             "clase": cache[f"clase::{k}"]["valor"], "respuesta": gen["respuesta"]}
        if x["respondible"]:
            f.update(metricas_recuperacion(x, rec["ranking"]))
            f.update({m: cache[f"{m}::{k}"]["valor"] for m in ("exactitud", "faithfulness", "answer_relevancy")})
            if "citadas" in gen:  # RetrieveAndGenerate: the references cited by the service
                nc, nb = len(gen["citadas"]), sum(1 for c in gen["citadas"] if sr.pasajes_en(tuple(c), x["gold"]))
            else:
                nc, nb = sg.citas(gen["respuesta"], ctx[k]["chunks"], x["gold"])
            f.update({"citas": nc, "citas_con_pasaje": nb,
                      "pasajes_en_contexto": metricas_recuperacion(x, rec["ranking"][:K_GEN])["recall@5"]})
            f["falla"] = "" if f["exactitud"] == 1 else ("recuperación" if f["pasajes_en_contexto"] < 1 else "generación")
        else:
            f["falla"] = "" if f["clase"] == "abstiene" else "generación (inventa)"
        filas.append(f)

    def media(fs, c):
        v = [r[c] for r in fs if r.get(c) is not None]
        return round(statistics.mean(v), 4) if v else None
    generador = (f"Bedrock RetrieveAndGenerate, {PERFIL_RAG}, plantilla predeterminada" if args.modo == "rag"
                 else f"{a.HAIKU} medium, prompt solo_documentos")
    resumen = {"backend": args.backend, "config": args.config, "modo": args.modo, "fecha": dt.date.today().isoformat(),
               "preguntas": len(items), "generador": generador, "juez": f"{a.HAIKU} low", "k_contexto": K_GEN,
               "chunks_fuera_del_tenant": sum(1 for kk, v in cache.items() if kk.startswith("rec::")
                                              and any(tn not in ("alfa", "None") for tn in v.get("tenants", []))),
               "recuperacion": {}, "generacion": {}, "costo_usd_por_consulta": {}, "latencia_s": {}, "fallas": []}
    for lang in ("es", "en"):
        r = [f for f in filas if f["lang"] == lang and f["respondible"]]
        s = [f for f in filas if f["lang"] == lang and not f["respondible"]]
        resumen["recuperacion"][lang] = {m: media(r, m) for m in MET_REC} | {"n": len(r)}
        nc = sum(f["citas"] for f in r)
        resumen["generacion"][lang] = {
            "n": len(r), "exactitud": media(r, "exactitud"), "faithfulness": media(r, "faithfulness"),
            "answer_relevancy": media(r, "answer_relevancy"),
            "precision_citas": round(sum(f["citas_con_pasaje"] for f in r) / nc, 4) if nc else None,
            "cobertura_cita": round(sum(1 for f in r if f["citas_con_pasaje"]) / len(r), 4) if r else None,
            "abstencion_falsa": f"{sum(f['clase'] == 'abstiene' for f in r)}/{len(r)}",
            "abstencion_correcta": f"{sum(f['clase'] == 'abstiene' for f in s)}/{len(s)}"}
    resumen["costo_usd_por_consulta"] = {"recuperacion": round(statistics.mean(f["costo_rec"] for f in filas), 6),
                                         "generacion": round(statistics.mean(f["costo_gen"] for f in filas), 6)}
    resumen["latencia_s"] = {e: {"p50": round(pct([f[c] for f in filas], 0.5), 2), "p95": round(pct([f[c] for f in filas], 0.95), 2)}
                             for e, c in (("recuperacion", "lat_rec"), ("generacion", "lat_gen"))}
    resumen["fallas"] = [{"id": f["id"], "lang": f["lang"], "atribucion": f["falla"], "respuesta": f["respuesta"][:200]}
                         for f in filas if f["falla"]]
    sin = sum(1 for kk, v in cache.items() if kk.split("::")[0] in ("faithfulness", "answer_relevancy", "exactitud", "clase")
              and v.get("valor") is None)
    resumen["metricas_sin_puntaje"] = sin
    resumen["costo_evaluacion_corrida_usd"] = round((uso["in"] * P["in"] + uso["out"] * P["out"]) / 1e6, 4)
    nres = [v["n_resultados"] for kk, v in cache.items() if kk.startswith("rec::") and "n_resultados" in v]
    if nres:
        resumen["resultados_por_consulta"] = {"media": round(statistics.mean(nres), 1), "cero": sum(1 for n in nres if n == 0),
                                              "menos_de_5": sum(1 for n in nres if n < 5)}
    resumen["rerank_fallido"] = sum(1 for kk, v in cache.items() if kk.startswith("rec::") and v.get("rerank_fallo"))
    (RES / f"{nombre}_resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (RES / f"{nombre}_detalle.csv").open("w", encoding="utf-8", newline="") as fh:
        campos = sorted({c for f in filas for c in f}, key=lambda c: (c == "respuesta", c))
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)

    print(f"## {nombre} ({len(items)} questions; generator: {generador})\n")
    print("### Retrieval suite (answerable questions)\n")
    print("| Language | n | " + " | ".join(MET_REC) + " |")
    print("|---|---|" + "---|" * len(MET_REC))
    for lang, m in resumen["recuperacion"].items():
        print(f"| {lang} | {m['n']} | " + " | ".join(f"{m[k]:.3f}" for k in MET_REC) + " |")
    print(f"\n### Generation suite over what was retrieved (top 5; {'RetrieveAndGenerate' if args.modo == 'rag' else 'common generator'})\n")
    print("| Language | n | accuracy | faithfulness | answer_relevancy | citation precision | citation coverage | false abstention | correct abstention |")
    print("|---|---|---|---|---|---|---|---|---|")
    for lang, g in resumen["generacion"].items():
        print(f"| {lang} | {g['n']} | {g['exactitud']:.3f} | {g['faithfulness']:.3f} | {g['answer_relevancy']:.3f} | "
              f"{g['precision_citas']:.3f} | {g['cobertura_cita']:.3f} | {g['abstencion_falsa']} | {g['abstencion_correcta']} |")
    print("\n### Cost and latency per query\n")
    print("| Stage | USD per query | p50 (s) | p95 (s) |\n|---|---|---|---|")
    for e in ("recuperacion", "generacion"):
        print(f"| {e} | ${resumen['costo_usd_por_consulta'][e]:.5f} | {resumen['latencia_s'][e]['p50']} | {resumen['latencia_s'][e]['p95']} |")
    print(f"\nFallas ({len(resumen['fallas'])}):")
    for f in resumen["fallas"]:
        print(f"- {f['id']} {f['lang']} ({f['atribucion']}): {f['respuesta'][:140]}")
    total = sum(f["costo_rec"] for f in filas) + sum(f["costo_gen"] for f in filas) + resumen["costo_evaluacion_corrida_usd"]
    if "resultados_por_consulta" in resumen:
        print(f"\nResults returned per query: {resumen['resultados_por_consulta']}")
    print(f"\nQueries with chunks from another tenant: {resumen['chunks_fuera_del_tenant']}. Metrics without a score: {sin}. Failed reranking: {resumen['rerank_fallido']}. Duration {time.time() - t0:.0f} s. "
          f"Cost (retrieval + generation of what was saved, and evaluation in this run): ${total:.4f}")


if __name__ == "__main__":
    main()
