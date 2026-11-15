"""Week 12, activity 7 (latency): the same machine, the same client, the same network and concurrency 1 for every option.

100 questions from the week 11 gold set (per language: 40 answerable and the 10 unanswerable). For each question, every
option runs in random order (seed 12), so that variation in the network and the moment favors none of them:
- propio            bge-m3 (LM Studio) + pgvector + reranking with Haiku 5.5 (the baseline);
- propio_sin_rerank the same up to pgvector (measured in the same call, before the reranking);
- bedrock_ctl       Bedrock Retrieve over ctl-chunks (S3 Vectors);
- bedrock_bda_rag   Bedrock RetrieveAndGenerate over adm-fijo-bda with Claude Haiku 4.5 (the full answer in one call);
- vertex_ctl_sem    Vertex AI Search vx-ctl, hybrid search + Ranking API;
- vertex_adm_sem    Vertex AI Search vx-adm, hybrid search + Ranking API.
Full answer = retrieval + the common generator (Haiku 5.5 medium, solo_documentos prompt, top 5), measured in series,
except RetrieveAndGenerate, which already includes it. Output: resultados/latencia_detalle.csv and latencia_resumen.json.
Cost: ≈ $0.30 (in-house reranking, 600 Haiku 5.5 generations and 100 RetrieveAndGenerate calls with Haiku 4.5).
"""
import csv
import json
import math
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import suites as s  # noqa: E402

a, sr, sg, sens = s.a, s.sr, s.sg, s.sens
RES = s.RES
CACHE = RES / "latencia_cache.json"


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, math.ceil(q * len(v)) - 1))]


def generar(x, ranking):
    chunks = [tuple(c) for c in ranking[:s.K_GEN]]
    t0 = time.perf_counter()
    texto, costo, _ = a.anthropic(a.HAIKU, "medium", sens.SIS_SOLO_DOCUMENTOS,
                                  f"Pregunta: {x['question']}\n\nContexto:\n{a.contexto(None, {'chunks': chunks})}")
    return time.perf_counter() - t0, costo


def main():
    items = [y for lang in ("es", "en") for resp, n in ((True, 40), (False, 10))
             for y in [z for z in sg.items_todos() if z["lang"] == lang and z["respondible"] == resp][:n]]
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    cli = s._aws("bedrock-agent-runtime")
    modelo = f"arn:aws:bedrock:us-east-1:{s._aws('sts').get_caller_identity()['Account']}:inference-profile/{s.PERFIL_RAG}"
    kb_bda = s._kb("adm-fijo-bda")
    rnd = random.Random(12)

    def ret(fn, x, *args):
        caja = {}
        fn([x], lambda _x, r: caja.update(r), *args)
        return caja

    for i, x in enumerate(items, 1):
        k = f"{x['id']}::{x['lang']}"
        if k in cache:
            continue
        fila = {}
        opciones = ["propio", "bedrock_ctl", "bedrock_bda_rag", "vertex_ctl_sem", "vertex_adm_sem"]
        rnd.shuffle(opciones)
        for op in opciones:
            if op == "propio":
                local = {}
                sr.recuperar([x], local)
                base, rer = local[f"base::{k}"], local[f"adoptado::{k}"]
                lg, cg = generar(x, rer["ranking"])
                lg2, cg2 = generar(x, base["ranking"])
                fila["propio"] = {"rec": rer["latencia_s"], "total": rer["latencia_s"] + lg, "costo_rec": rer["costo"], "costo_gen": cg}
                fila["propio_sin_rerank"] = {"rec": base["latencia_s"], "total": base["latencia_s"] + lg2, "costo_rec": 0.0, "costo_gen": cg2}
            elif op == "bedrock_bda_rag":
                t0 = time.perf_counter()
                r = cli.retrieve_and_generate(input={"text": x["question"]}, retrieveAndGenerateConfiguration={
                    "type": "KNOWLEDGE_BASE", "knowledgeBaseConfiguration": {"knowledgeBaseId": kb_bda, "modelArn": modelo,
                        "retrievalConfiguration": {"vectorSearchConfiguration": {"numberOfResults": s.K_GEN, "filter": s.FILTRO_ALFA}}}})
                lat = time.perf_counter() - t0
                fila[op] = {"rec": None, "total": lat, "costo_rec": 0.0,
                            "costo_gen": ((1500 + len(x["question"]) + 2000) / 4 * s.PRECIO_HAIKU45["in"]
                                          + len(r["output"]["text"]) / 4 * s.PRECIO_HAIKU45["out"]) / 1e6}
            else:
                fn, cfg = {"bedrock_ctl": (s.recuperar_bedrock, "ctl-chunks"), "vertex_ctl_sem": (s.recuperar_vertex, "vx-ctl:semantico"),
                           "vertex_adm_sem": (s.recuperar_vertex, "vx-adm:semantico")}[op]
                r = ret(fn, x, cfg)
                lg, cg = generar(x, r["ranking"])
                fila[op] = {"rec": r["latencia_s"], "total": r["latencia_s"] + lg, "costo_rec": r["costo"], "costo_gen": cg}
        cache[k] = fila
        CACHE.write_text(json.dumps(cache) + "\n", encoding="utf-8")
        print(f"{i}/{len(items)} {k}: " + ", ".join(f"{o} {v['total']:.1f}s" for o, v in fila.items()), flush=True)

    ops = list(next(iter(cache.values())).keys())
    resumen, filas = {"preguntas": len(cache), "concurrencia": 1, "orden": "aleatorio por pregunta (semilla 12)"}, []
    for o in ops:
        rec = [v[o]["rec"] for v in cache.values() if v[o]["rec"] is not None]
        tot = [v[o]["total"] for v in cache.values()]
        resumen[o] = {"recuperacion_p50": round(pct(rec, .5), 2) if rec else None, "recuperacion_p95": round(pct(rec, .95), 2) if rec else None,
                      "total_p50": round(pct(tot, .5), 2), "total_p95": round(pct(tot, .95), 2),
                      "costo_rec_media": round(sum(v[o]["costo_rec"] for v in cache.values()) / len(cache), 6),
                      "costo_gen_media": round(sum(v[o]["costo_gen"] for v in cache.values()) / len(cache), 6)}
    for k, v in cache.items():
        for o in ops:
            filas.append({"pregunta": k, "opcion": o, **v[o]})
    (RES / "latencia_resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (RES / "latencia_detalle.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["pregunta", "opcion", "rec", "total", "costo_rec", "costo_gen"])
        w.writeheader()
        w.writerows(filas)
    print("\n| Option | Retrieval p50 | Retrieval p95 | Full answer p50 | Full answer p95 |")
    print("|---|---|---|---|---|")
    for o in ops:
        r = resumen[o]
        print(f"| {o} | {r['recuperacion_p50'] or '-'} | {r['recuperacion_p95'] or '-'} | {r['total_p50']} | {r['total_p95']} |")


if __name__ == "__main__":
    main()
