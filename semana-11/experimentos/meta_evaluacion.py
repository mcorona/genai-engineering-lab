"""Week 11, activity 3: validating the generation metrics (meta-evaluation).

Sample: 20 questions per language (the same in ES and EN), 15 base and 5 non-text, chosen with seed 11 among the
answerable questions whose reference carries at least one figure that does not come from the question. Context: the top 5
of activity 2's adopted pipeline (resultados/suite_recuperacion_cache.json); all of them have their passage in that top 5.

Answer variants (built with fixed rules, without a model):
- control: the activity 1 reference (faithful and relevant).
- cifra_cambiada: the first figure of the reference that does not come from the question (preferably one from the context;
  never a year), × 1.5 (or × 2, 3, 5, 7, 10, 0.9, 0.5 if the new value already appears in the context or the question, or if a
  percentage would exceed 100), with the same format.
- inventada: the reference plus a plausible sentence that is not in the context (a fixed template per language).
- fuera_de_tema: the reference of another question in the sample, from another document (true, but it does not answer).
- evasiva: a generic refusal ("I don't have enough information…").

Metrics, per judge (Haiku 5.5 low and Sonnet 5.5 low): RAGAS 0.4.3 faithfulness and answer relevancy (bge-m3
embeddings from LM Studio), and accuracy with the in-house judge of weeks 8 and 10 (SIS_JUEZ in semana-10/experimentos/asistente.py).

Criteria, fixed before the run:
- A metric detects a variant if the paired difference variant − control has a 95 % bootstrap CI (2,000
  resamples, seed 11) below 0 and the variant scores below the control on at least 80 % of the questions
  (ties count 0.5).
- Expected detections: faithfulness detects cifra_cambiada and inventada; answer relevancy detects fuera_de_tema and
  evasiva. The control must have a mean faithfulness >= 0.9.
- Decision: the cheapest judge that meets the four expected detections and the control. If none meets everything, the
  one that meets the most, with what is missing documented.
RAGAS judge: Haiku with llm_factory (Instructor's TOOLS mode); Sonnet with Instructor's JSON mode, because Sonnet 5.5
rejects the forced tool_choice. Each judge has its own disk cache (RAGAS's key does not include the model).
Cache per judge, metric, question and variant in resultados/meta_evaluacion_cache.json (plus the judge's disk cache).
Requires LM Studio with bge-m3 and ANTHROPIC_API_KEY.
"""
import asyncio
import csv
import json
import random
import re
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REPO = RAIZ.parent
RES = RAIZ / "resultados"
CACHE = RES / "meta_evaluacion_cache.json"
PRECIOS = json.loads((REPO / "semana-07" / "prices.json").read_text(encoding="utf-8"))
JUECES = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5"}
MODOS = {"haiku": "Instructor TOOLS", "sonnet": "Instructor JSON"}
VARIANTES = ("control", "cifra_cambiada", "inventada", "fuera_de_tema", "evasiva")
ESPERADAS = {("faithfulness", "cifra_cambiada"), ("faithfulness", "inventada"),
             ("answer_relevancy", "fuera_de_tema"), ("answer_relevancy", "evasiva")}
CONCURRENCIA = 2  # run 2: unstable network (timeouts with 8 in parallel)
INVENTADA = {"es": "Además, esta regla solo aplica a pedidos internacionales y requiere la firma del director general.",
             "en": "In addition, this rule applies only to international orders and requires the CEO's signature."}
EVASIVA = {"es": "No tengo suficiente información para responder con precisión.",
           "en": "I don't have enough information to answer precisely."}
SIS_JUEZ = ("Eres un evaluador estricto. Recibes una pregunta, la referencia correcta y la respuesta de un asistente. La "
            "respuesta es correcta si contiene la información esencial de la referencia sin contradecirla (puede agregar "
            "detalles o citas). Si la referencia es una lista o un conjunto de filas, la respuesta debe incluir esos "
            "elementos. Responde SOLO con JSON: {\"correcta\": true} o {\"correcta\": false}.")  # copy from week 10
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def norm(s):
    return " ".join(s.replace("**", "").lower().split())


def numeros(t):
    return {n.replace(",", "").rstrip(".") for n in NUM.findall(t)}


def cambiar_cifra(texto, contexto, pregunta):
    """Changes the first figure of the reference that does not come from the question (preferably one that is in the
    context), so that the error falls on the answer's data and not on the repetition of the question."""
    en_ctx, en_preg = numeros(contexto), numeros(pregunta)
    cands = [m for m in NUM.finditer(texto) if m.group(0).replace(",", "").rstrip(".") not in en_preg
             and not re.fullmatch(r"(19|20)\d\d", m.group(0).rstrip("."))]  # no years
    cands = [m for m in cands if m.group(0).replace(",", "").rstrip(".") in en_ctx] or cands
    if not cands:
        raise ValueError(f"sin cifra propia de la respuesta: {texto}")
    m = cands[0]
    crudo = m.group(0).rstrip(".")
    dec = len(crudo.split(".")[1]) if "." in crudo else 0
    valor = float(crudo.replace(",", ""))
    porcentaje = texto[m.start() + len(crudo):].lstrip().startswith("%")
    for factor in (1.5, 2, 3, 5, 7, 10, 0.9, 0.5):
        nuevo = valor * factor if valor else factor
        if porcentaje and nuevo > 100:  # an impossible percentage would be too easy to detect
            continue
        s = f"{nuevo:,.{dec}f}" if "," in crudo else f"{nuevo:.{dec}f}"
        if s != crudo and s.replace(",", "") not in en_ctx | en_preg:
            return texto[:m.start()] + s + texto[m.start() + len(crudo):]
    raise ValueError(f"no se pudo cambiar la cifra de: {texto}")


def muestra():
    ref = {lang: {x["id"]: x for l in (RAIZ / "datasets" / f"eval_rag_{lang}.jsonl").read_text(encoding="utf-8").splitlines()
                  if (x := json.loads(l))["respondible"]} for lang in ("es", "en")}
    ids = [i for i in ref["es"] if i in ref["en"] and all(numeros(ref[l][i]["referencia"]) - numeros(ref[l][i]["question"])
                                                          for l in ("es", "en"))]
    rnd = random.Random(11)
    elegidos = rnd.sample([i for i in ids if ref["es"][i]["tipo"] == "base"], 15) + \
        rnd.sample([i for i in ids if ref["es"][i]["tipo"] != "base"], 5)
    return ref, elegidos


def construir(ref, elegidos, rec):
    casos = []
    for lang in ("es", "en"):
        fuentes = {i: {Path(g["source"]).stem for g in ref[lang][i]["gold"]} for i in elegidos}
        for n, i in enumerate(elegidos):
            x = ref[lang][i]
            ctx = [c for _, c in rec[f"adoptado::{i}::{lang}"]["ranking"][:5]]
            if not any(norm(g["passage"]) in norm(c) for g in x["gold"] for c in ctx):
                raise SystemExit(f"{i} {lang}: the passage is not in the activity 2 top 5")
            otro = next(elegidos[(n + k) % len(elegidos)] for k in range(1, len(elegidos))
                        if not fuentes[elegidos[(n + k) % len(elegidos)]] & fuentes[i])
            respuestas = {"control": x["referencia"],
                          "cifra_cambiada": cambiar_cifra(x["referencia"], "\n".join(ctx), x["question"]),
                          "inventada": x["referencia"].rstrip() + " " + INVENTADA[lang],
                          "fuera_de_tema": ref[lang][otro]["referencia"],
                          "evasiva": EVASIVA[lang]}
            for v in VARIANTES:
                casos.append({"id": i, "lang": lang, "tipo": x["tipo"], "variante": v, "question": x["question"],
                              "referencia": x["referencia"], "respuesta": respuestas[v], "contextos": ctx,
                              "fuera_de_tema_de": otro if v == "fuera_de_tema" else ""})
    return casos


async def evaluar(casos, cache, guardar):
    from anthropic import AsyncAnthropic
    from openai import AsyncOpenAI
    from ragas.cache import DiskCacheBackend
    from ragas.embeddings.base import embedding_factory
    from ragas.llms import llm_factory
    from ragas.metrics.collections import AnswerRelevancy, Faithfulness
    import os

    emb = embedding_factory("openai", model=os.getenv("LMSTUDIO_EMBED_MODEL", "text-embedding-bge-m3"),
                            client=AsyncOpenAI(base_url=os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1"), api_key="lm-studio"))
    uso, metricas, clientes = {}, {}, {}
    for j, modelo in JUECES.items():
        uso[j] = {"in": 0, "out": 0, "llamadas": 0}
        cliente = AsyncAnthropic(max_retries=4, timeout=180)
        crear = cliente.messages.create

        async def crear_contando(*a, _crear=crear, _u=uso[j], **k):
            r = await _crear(*a, **k)
            _u["in"] += r.usage.input_tokens
            _u["out"] += r.usage.output_tokens
            _u["llamadas"] += 1
            return r
        cliente.messages.create = crear_contando
        clientes[j] = cliente
        # Run 2: the RAGAS cache key does not include the model, so in run 1 Sonnet received the
        # answers that Haiku had left in the cache. Now each judge has its own cache.
        cache_j = DiskCacheBackend(str(Path.home() / ".cache" / ("ragas_semana11" if j == "haiku" else f"ragas_semana11_{j}")))
        if j == "haiku":
            llm = llm_factory(modelo, provider="anthropic", client=cliente, max_tokens=4000,
                              extra_body={"output_config": {"effort": "low"}}, cache=cache_j)
        else:
            # Sonnet 5.5 rejects the forced tool_choice of Instructor's TOOLS mode (HTTP 400): JSON mode.
            import instructor
            from ragas.llms.base import InstructorLLM, InstructorModelArgs
            llm = InstructorLLM(client=instructor.from_anthropic(cliente, mode=instructor.Mode.ANTHROPIC_JSON), model=modelo,
                                provider="anthropic", model_args=InstructorModelArgs(), cache=cache_j, max_tokens=4000,
                                extra_body={"output_config": {"effort": "low"}})
        llm.model_args["max_retries"] = 3
        llm.model_args.pop("temperature", None)
        llm.model_args.pop("top_p", None)
        metricas[j] = {"faithfulness": Faithfulness(llm=llm), "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=emb)}
    sem = asyncio.Semaphore(CONCURRENCIA)

    async def juez_propio(j, c):
        r = await clientes[j].messages.create(
            model=JUECES[j], max_tokens=2000, system=SIS_JUEZ, extra_body={"output_config": {"effort": "low"}},
            messages=[{"role": "user", "content": f"Pregunta: {c['question']}\n\nReferencia correcta:\n{c['referencia']}"
                                                  f"\n\nRespuesta del asistente:\n{c['respuesta']}"}])
        t = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        m = re.search(r"\{.*?\}", t, re.S)
        return float(bool(json.loads(m.group(0))["correcta"])) if m else None

    async def uno(j, metrica, c):
        k = f"{j}::{metrica}::{c['id']}::{c['lang']}::{c['variante']}"
        if k in cache:
            return
        async with sem:
            try:
                if metrica == "exactitud_propia":
                    v = await juez_propio(j, c)
                elif metrica == "faithfulness":
                    v = (await metricas[j][metrica].ascore(user_input=c["question"], response=c["respuesta"],
                                                           retrieved_contexts=c["contextos"])).value
                else:
                    v = (await metricas[j][metrica].ascore(user_input=c["question"], response=c["respuesta"])).value
                cache[k] = {"valor": v}
            except Exception as e:  # noqa: BLE001
                cache[k] = {"valor": None, "error": type(e).__name__}
        guardar()
    await asyncio.gather(*(uno(j, m, c) for j in JUECES for m in ("faithfulness", "answer_relevancy", "exactitud_propia")
                           for c in casos))
    return uso


def bootstrap(dif, n=2000, semilla=11):
    rnd = random.Random(semilla)
    medias = sorted(statistics.mean(rnd.choice(dif) for _ in dif) for _ in range(n))
    return statistics.mean(dif), medias[int(0.025 * n)], medias[int(0.975 * n) - 1]


def main():
    rec = json.loads((RES / "suite_recuperacion_cache.json").read_text(encoding="utf-8"))
    ref, elegidos = muestra()
    casos = construir(ref, elegidos, rec)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    def guardar():
        CACHE.write_text(json.dumps(cache, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"sample: {elegidos}", file=sys.stderr)
    uso = asyncio.run(evaluar(casos, cache, guardar))
    guardar()

    filas = []
    for c in casos:
        for j in JUECES:
            for m in ("faithfulness", "answer_relevancy", "exactitud_propia"):
                v = cache[f"{j}::{m}::{c['id']}::{c['lang']}::{c['variante']}"]
                filas.append({"juez": j, "metrica": m, "id": c["id"], "lang": c["lang"], "tipo": c["tipo"],
                              "variante": c["variante"], "valor": v["valor"], "error": v.get("error", ""),
                              "respuesta": c["respuesta"]})
    with (RES / "meta_evaluacion_detalle.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)

    def valores(j, m, v, lang=None):
        return {(f["id"], f["lang"]): f["valor"] for f in filas if f["juez"] == j and f["metrica"] == m
                and f["variante"] == v and (lang is None or f["lang"] == lang) and f["valor"] is not None}

    print("## Means per judge, metric and variant (ES / EN / both)\n")
    print("| Judge | Metric | " + " | ".join(VARIANTES) + " |")
    print("|---|---|" + "---|" * len(VARIANTES))
    for j in JUECES:
        for m in ("faithfulness", "answer_relevancy", "exactitud_propia"):
            celdas = []
            for v in VARIANTES:
                es, en, ab = (valores(j, m, v, l) for l in ("es", "en", None))
                celdas.append(f"{statistics.mean(es.values()):.2f} / {statistics.mean(en.values()):.2f} / {statistics.mean(ab.values()):.2f}")
            print(f"| {j} | {m} | " + " | ".join(celdas) + " |")

    print("\n## Separation of each variant from the control (both languages, n = 40 pairs)\n")
    print("| Judge | Metric | Variant | Expected | Mean difference | 95 % CI | Variant < control | Detects |")
    print("|---|---|---|---|---|---|---|---|")
    veredicto = {}
    for j in JUECES:
        for m in ("faithfulness", "answer_relevancy", "exactitud_propia"):
            ctl = valores(j, m, "control")
            for v in VARIANTES[1:]:
                var = valores(j, m, v)
                pares = [(ctl[k], var[k]) for k in ctl if k in var]
                dif = [b - a for a, b in pares]
                media, lo, hi = bootstrap(dif)
                tasa = sum(1 if b < a else 0.5 if b == a else 0 for a, b in pares) / len(pares)
                detecta = hi < 0 and tasa >= 0.8
                veredicto[(j, m, v)] = detecta
                print(f"| {j} | {m} | {v} | {'sí' if (m, v) in ESPERADAS else 'no'} | {media:+.3f} | [{lo:+.3f}, {hi:+.3f}] | "
                      f"{tasa:.2f} ({len(pares)}) | {'sí' if detecta else 'no'} |")

    print("\n## Decision\n")
    for j, modelo in JUECES.items():
        ctl = statistics.mean(valores(j, "faithfulness", "control").values())
        ok = [mv for mv in sorted(ESPERADAS) if veredicto[(j, *mv)]]
        p = PRECIOS[f"anthropic:{modelo}"]
        costo = (uso[j]["in"] * p["in"] + uso[j]["out"] * p["out"]) / 1e6
        errores = sum(1 for f in filas if f["juez"] == j and f["valor"] is None)
        print(f"- {j} ({MODOS[j]}): expected detections {len(ok)}/4 {ok}; control faithfulness {ctl:.3f} "
              f"({'meets' if ctl >= 0.9 else 'does NOT meet'} >= 0.9); without a score {errores}; cost of this run ${costo:.4f} "
              f"({uso[j]['llamadas']} calls, {uso[j]['in']} input tokens and {uso[j]['out']} output tokens)")


if __name__ == "__main__":
    main()
