"""Week 11, activity 4: the generation suite (does not depend on the retriever).

Gold set: the full datasets/eval_rag_{es,en}.jsonl (75 per language: 65 answerable and 10 unanswerable).

A fixed context, frozen in resultados/contextos_generacion.json before generating:
- answerable: one chunk of the activity 7 index per reference passage (the best-ranked one that contains it) plus
  k distractors (k between 2 and 4, random with seed 11), drawn at random from the 10 best-ranked candidates that
  contain no reference passage (hard distractors: from the same corpus and similar to the question). The rankings
  are those of activity 2's adopted pipeline (resultados/suite_recuperacion_cache.json).
- unanswerable: k between 3 and 5 chunks drawn at random from the 10 most similar to the question (bge-m3, same filter).
- the order of the chunks is shuffled with seed 11.

Generator: the week 10 assistant's (Haiku 5.5 medium, SIS_RESP, chunks as [D1]..[Dn]).

Metrics (judge Haiku 5.5 low, the activity 3 decision):
- answerable: faithfulness and answer relevancy (RAGAS 0.4.3, bge-m3), accuracy against the reference (the in-house
  judge of weeks 8 and 10), citation precision (citations [Dn] whose chunk contains a reference passage / citations) and
  citation coverage (answers that cite at least one chunk with the passage).
- all: classification of the answer as "abstiene" (it says the information is not in the documents and gives no figure
  as the answer) or "responde" (judge Haiku 5.5 low). For the unanswerable ones: the correct-abstention rate and the
  invented-answer rate (= responde). For the answerable ones: the false-abstention rate.
- cost per query: generation and evaluation separately; p50 latency of the generation.
Cache per question and metric in resultados/suite_generacion_cache.json; the judge's disk cache separated by model.
Requires LM Studio with bge-m3 and ANTHROPIC_API_KEY; NLQ_DSN only the first time (contexts of the unanswerable questions).
"""
import asyncio
import csv
import json
import os
import random
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import suite_recuperacion as sr  # noqa: E402  (also imports the week 10 assistant)

a = sr.a
RES = RAIZ / "resultados"
CONTEXTOS = RES / "contextos_generacion.json"
CACHE = RES / "suite_generacion_cache.json"
PRECIO = a.PRECIOS[f"anthropic:{a.HAIKU}"]
HILOS, CONCURRENCIA = 8, 8
SIS_CLASE = ("Recibes una pregunta y la respuesta de un asistente que solo puede usar documentos internos. Clasifica la "
             "respuesta: \"abstiene\" si dice que la información no está en los documentos o en el contexto y no da un dato "
             "como respuesta a la pregunta; \"responde\" si da una respuesta a la pregunta, aunque agregue advertencias. "
             "Responde SOLO con JSON: {\"clase\": \"abstiene\"} o {\"clase\": \"responde\"}.")


def items_todos():
    return [x for lang in ("es", "en") for l in (RAIZ / "datasets" / f"eval_rag_{lang}.jsonl").read_text(encoding="utf-8").splitlines()
            for x in [json.loads(l)]]


def construir_contextos(items):
    rec = json.loads((RES / "suite_recuperacion_cache.json").read_text(encoding="utf-8"))
    sin = [x for x in items if not x["respondible"]]
    local = {}
    sr.recuperar(sin, local)  # top 20 by similarity (and its reranking, which is not used here)
    rnd = random.Random(11)
    ctx = {}
    for x in items:
        k = f"{x['id']}::{x['lang']}"
        if x["respondible"]:
            ranking = [tuple(c) for c in rec[f"adoptado::{k}"]["ranking"]]
            oro = []
            for i, g in enumerate(x["gold"]):
                c = next(c for c in ranking if i in sr.pasajes_en(c, x["gold"]))
                if c not in oro:
                    oro.append(c)
            distract = [c for c in ranking if not sr.pasajes_en(c, x["gold"])][:10]
            elegidos = oro + rnd.sample(distract, rnd.randint(2, 4))
        else:
            ranking = [tuple(c) for c in local[f"base::{k}"]["ranking"]][:10]
            oro = []
            elegidos = rnd.sample(ranking, rnd.randint(3, 5))
        rnd.shuffle(elegidos)
        ctx[k] = {"chunks": [list(c) for c in elegidos], "n_oro": len(oro) if x["respondible"] else 0}
    CONTEXTOS.write_text(json.dumps(ctx, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return ctx


def generar(items, ctx, cache, guardar, sistema=None):
    """sistema: the generator's prompt; by default the week 10 assistant's (a.SIS_RESP). Activity 6 changes it."""
    def uno(x):
        k = f"gen::{x['id']}::{x['lang']}"
        if k in cache:
            return
        chunks = [tuple(c) for c in ctx[f"{x['id']}::{x['lang']}"]["chunks"]]
        t0 = time.perf_counter()
        texto, costo, _ = a.anthropic(a.HAIKU, "medium", sistema or a.SIS_RESP,
                                      f"Pregunta: {x['question']}\n\nContexto:\n{a.contexto(None, {'chunks': chunks})}")
        cache[k] = {"respuesta": texto, "costo": costo, "latencia_s": round(time.perf_counter() - t0, 3)}
        guardar()
    with ThreadPoolExecutor(HILOS) as ex:
        list(ex.map(uno, items))


async def evaluar(items, ctx, cache, guardar):
    from anthropic import AsyncAnthropic
    from openai import AsyncOpenAI
    from ragas.cache import DiskCacheBackend
    from ragas.embeddings.base import embedding_factory
    from ragas.llms import llm_factory
    from ragas.metrics.collections import AnswerRelevancy, Faithfulness

    uso = {"in": 0, "out": 0, "llamadas": 0}
    cliente = AsyncAnthropic(max_retries=4, timeout=180)
    crear = cliente.messages.create

    async def crear_contando(*args, **kw):
        r = await crear(*args, **kw)
        uso["in"] += r.usage.input_tokens
        uso["out"] += r.usage.output_tokens
        uso["llamadas"] += 1
        return r
    cliente.messages.create = crear_contando
    juez = llm_factory(a.HAIKU, provider="anthropic", client=cliente, max_tokens=4000,
                       extra_body={"output_config": {"effort": "low"}},
                       cache=DiskCacheBackend(str(Path.home() / ".cache" / "ragas_semana11")))  # Haiku cache (activity 3)
    juez.model_args["max_retries"] = 3
    juez.model_args.pop("temperature", None)
    juez.model_args.pop("top_p", None)
    emb = embedding_factory("openai", model=os.getenv("LMSTUDIO_EMBED_MODEL", "text-embedding-bge-m3"),
                            client=AsyncOpenAI(base_url=os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1"), api_key=os.getenv("EMB_API_KEY", "lm-studio")))  # EMB_API_KEY: CI with OpenAI
    faith, relev = Faithfulness(llm=juez), AnswerRelevancy(llm=juez, embeddings=emb)
    sem = asyncio.Semaphore(CONCURRENCIA)

    async def json_juez(sistema, contenido, campo):
        r = await cliente.messages.create(model=a.HAIKU, max_tokens=2000, system=sistema,
                                          extra_body={"output_config": {"effort": "low"}},
                                          messages=[{"role": "user", "content": contenido}])
        t = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        m = re.search(r"\{.*?\}", t, re.S)
        return json.loads(m.group(0))[campo] if m else None

    async def uno(metrica, x):
        k = f"{metrica}::{x['id']}::{x['lang']}"
        if k in cache:
            return
        resp = cache[f"gen::{x['id']}::{x['lang']}"]["respuesta"]
        textos = [c for _, c in ctx[f"{x['id']}::{x['lang']}"]["chunks"]]
        async with sem:
            try:
                if metrica == "faithfulness":
                    v = (await faith.ascore(user_input=x["question"], response=resp, retrieved_contexts=textos)).value
                elif metrica == "answer_relevancy":
                    v = (await relev.ascore(user_input=x["question"], response=resp)).value
                elif metrica == "exactitud":
                    c = await json_juez(a.SIS_JUEZ, f"Pregunta: {x['question']}\n\nReferencia correcta:\n{x['referencia']}"
                                                    f"\n\nRespuesta del asistente:\n{resp}", "correcta")
                    v = None if c is None else float(bool(c))
                else:
                    v = await json_juez(SIS_CLASE, f"Pregunta: {x['question']}\n\nRespuesta:\n{resp}", "clase")
                cache[k] = {"valor": v}
            except Exception as e:  # noqa: BLE001
                cache[k] = {"valor": None, "error": type(e).__name__}
        guardar()
    tareas = [uno("clase", x) for x in items]
    tareas += [uno(m, x) for x in items if x["respondible"] for m in ("faithfulness", "answer_relevancy", "exactitud")]
    await asyncio.gather(*tareas)
    return uso


def citas(resp, chunks, gold):
    n = sorted({int(d) for d in re.findall(r"\[D(\d+)\]", resp) if 0 < int(d) <= len(chunks)})
    buenas = [d for d in n if sr.pasajes_en(tuple(chunks[d - 1]), gold)]
    return len(n), len(buenas)


def main():
    items = items_todos()
    ctx = json.loads(CONTEXTOS.read_text(encoding="utf-8")) if CONTEXTOS.exists() else construir_contextos(items)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    def guardar():
        CACHE.write_text(json.dumps(cache, ensure_ascii=False) + "\n", encoding="utf-8")
    generar(items, ctx, cache, guardar)
    uso = asyncio.run(evaluar(items, ctx, cache, guardar))
    guardar()

    filas = []
    for x in items:
        k = f"{x['id']}::{x['lang']}"
        g = cache[f"gen::{k}"]
        f = {"id": x["id"], "lang": x["lang"], "tipo": "sin_respuesta" if not x["respondible"] else
             ("no_textual" if x["tipo"].startswith("no_textual") else "base"), "n_chunks": len(ctx[k]["chunks"]),
             "clase": cache[f"clase::{k}"]["valor"], "costo_gen": g["costo"], "latencia_s": g["latencia_s"], "respuesta": g["respuesta"]}
        if x["respondible"]:
            nc, nb = citas(g["respuesta"], ctx[k]["chunks"], x["gold"])
            f.update({m: cache[f"{m}::{k}"]["valor"] for m in ("faithfulness", "answer_relevancy", "exactitud")})
            f.update({"citas": nc, "citas_con_pasaje": nb})
        filas.append(f)
    with (RES / "suite_generacion_detalle.csv").open("w", encoding="utf-8", newline="") as fh:
        campos = sorted({c for f in filas for c in f}, key=lambda c: (c == "respuesta", c))
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)

    def media(f, c):
        v = [r[c] for r in f if r.get(c) is not None]
        return f"{statistics.mean(v):.3f}" if v else "-"

    print("## Respondibles\n")
    print("| Language | Type | n | faithfulness | answer_relevancy | accuracy (in-house judge) | citation precision | citation coverage | false abstention |")
    print("|---|---|---|---|---|---|---|---|---|")
    for lang in ("es", "en"):
        for tipo in ("base", "no_textual", "todas"):
            f = [r for r in filas if r["lang"] == lang and r["tipo"] != "sin_respuesta" and (tipo == "todas" or r["tipo"] == tipo)]
            nc = sum(r["citas"] for r in f)
            prec = f"{sum(r['citas_con_pasaje'] for r in f) / nc:.3f} ({nc})" if nc else "-"
            cob = sum(1 for r in f if r["citas_con_pasaje"]) / len(f)
            print(f"| {lang} | {tipo} | {len(f)} | {media(f, 'faithfulness')} | {media(f, 'answer_relevancy')} | {media(f, 'exactitud')} | "
                  f"{prec} | {cob:.3f} | {sum(r['clase'] == 'abstiene' for r in f)}/{len(f)} |")
    print("\n## Unanswerable\n")
    print("| Language | n | Correct abstention | Invented answer | Unclassified |")
    print("|---|---|---|---|---|")
    for lang in ("es", "en"):
        f = [r for r in filas if r["lang"] == lang and r["tipo"] == "sin_respuesta"]
        print(f"| {lang} | {len(f)} | {sum(r['clase'] == 'abstiene' for r in f)}/{len(f)} | {sum(r['clase'] == 'responde' for r in f)}/{len(f)} | "
              f"{sum(r['clase'] not in ('abstiene', 'responde') for r in f)} |")
    print("\n## By number of chunks in the context (answerable questions, both languages)\n")
    print("| Chunks | n | faithfulness | accuracy | citation precision |")
    print("|---|---|---|---|---|")
    for n in sorted({r["n_chunks"] for r in filas if r["tipo"] != "sin_respuesta"}):
        f = [r for r in filas if r["tipo"] != "sin_respuesta" and r["n_chunks"] == n]
        nc = sum(r["citas"] for r in f)
        print(f"| {n} | {len(f)} | {media(f, 'faithfulness')} | {media(f, 'exactitud')} | "
              f"{sum(r['citas_con_pasaje'] for r in f) / nc:.3f} |" if nc else f"| {n} | {len(f)} | - | - | - |")
    print("\n## Cases to review\n")
    for r in filas:
        motivo = []
        if r["tipo"] == "sin_respuesta" and r["clase"] != "abstiene":
            motivo.append("inventó una respuesta")
        if r["tipo"] != "sin_respuesta":
            if r["clase"] == "abstiene":
                motivo.append("abstención falsa")
            if r.get("exactitud") == 0:
                motivo.append("incorrecta según el juez propio")
            if r.get("faithfulness") is not None and r["faithfulness"] < 0.5:
                motivo.append(f"faithfulness {r['faithfulness']:.2f}")
        if motivo:
            print(f"- {r['id']} {r['lang']} ({', '.join(motivo)}): {r['respuesta'][:160].replace(chr(10), ' ')}")
    sin = sum(1 for k, v in cache.items() if not k.startswith("gen::") and v.get("valor") is None)
    costo_gen = sum(r["costo_gen"] for r in filas)
    costo_ev = (uso["in"] * PRECIO["in"] + uso["out"] * PRECIO["out"]) / 1e6
    print(f"\nWithout a judge score: {sin}")
    print(f"Cost: generation ${costo_gen:.4f} (${costo_gen / len(filas):.5f} per query; p50 latency "
          f"{statistics.median(r['latencia_s'] for r in filas):.1f} s); evaluation in this run ${costo_ev:.4f} "
          f"({uso['llamadas']} calls; what was already cached is not billed)")


if __name__ == "__main__":
    main()
