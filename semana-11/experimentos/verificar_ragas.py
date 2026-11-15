"""Week 11, a prerequisite: checks RAGAS with an Anthropic judge and bge-m3 embeddings from LM Studio.

Records the versions and runs 4 RAGAS metrics (the modern API, ragas.metrics.collections) on 4 cases with a
known result, built from a literal passage of semana-08/corpus/devoluciones.md:
- fiel: a correct answer supported by the context (high faithfulness and answer relevance);
- cifra_cambiada: "45 días" instead of "30 días" (faithfulness must drop);
- fuera_de_tema: a true answer that does not answer the question (answer relevance must drop);
- contexto_equivocado: a context without the reference passage (context recall must drop).
It is not the activity 3 meta-evaluation (that one uses 20 questions per language): it only confirms that the setup
works and that the metrics move in the expected direction. It records the judge's tokens and cost.

Configuration:
- Judge: llm_factory(model, provider="anthropic", client=AsyncAnthropic()). The ragas.metrics.collections metrics
  call agenerate(), so the client has to be asynchronous (with Anthropic() they fail with a TypeError). RAGAS sends
  temperature=0.01 and top_p=0.1 by default; current Claude models do not accept both, so both are removed. The effort goes in
  extra_body.output_config (Haiku's default: medium) and max_tokens goes up to 4000 because reasoning counts as output.
- Embeddings: embedding_factory("openai", model=LMSTUDIO_EMBED_MODEL, client=AsyncOpenAI(base_url=LM Studio)).
Requires ANTHROPIC_API_KEY and LM Studio with bge-m3. Usage: python verificar_ragas.py [--modelo ...] [--esfuerzo low]
"""
import argparse
import importlib.metadata as md
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PRECIOS = json.loads((REPO / "semana-07" / "prices.json").read_text(encoding="utf-8"))

PREGUNTA = "¿Cuál es el plazo para que un cliente devuelva un producto?"
REFERENCIA = "El cliente tiene 30 días naturales desde la entrega para devolver un producto."
CONTEXTO = ["- Plazo: **30 días naturales** desde la entrega.\n- El producto debe estar en su empaque original y sin uso.\n"
            "- La nota de crédito se emite en un máximo de **10 días hábiles** después de recibir la devolución."]
CONTEXTO_OTRO = ["- Por defecto de calidad: dentro de los **15 días** siguientes a la recepción.\n"
                 "- Por exceso de entrega: se devuelve la diferencia o se negocia su aceptación con nota de cargo."]
CASOS = {
    "fiel": (CONTEXTO, "El plazo es de 30 días naturales desde la entrega, con el producto en su empaque original y sin uso."),
    "cifra_cambiada": (CONTEXTO, "El plazo es de 45 días naturales desde la entrega."),
    "fuera_de_tema": (CONTEXTO, "La nota de crédito se emite en un máximo de 10 días hábiles."),
    "contexto_equivocado": (CONTEXTO_OTRO, "No tengo ese dato en el contexto."),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", default="claude-haiku-5-5")
    ap.add_argument("--esfuerzo", default="low", choices=["low", "medium", "high"])
    args = ap.parse_args()

    for pkg in ("ragas", "langchain-community", "langchain-core", "instructor", "anthropic", "openai"):
        try:
            print(f"{pkg}=={md.version(pkg)}")
        except md.PackageNotFoundError:
            print(f"{pkg}: not installed")

    from anthropic import AsyncAnthropic
    from openai import AsyncOpenAI
    from ragas.embeddings.base import embedding_factory
    from ragas.llms import llm_factory
    from ragas.metrics.collections import AnswerRelevancy, ContextRecall, Faithfulness

    uso = {"in": 0, "out": 0, "llamadas": 0}
    cliente = AsyncAnthropic()
    crear = cliente.messages.create

    async def crear_contando(*a, **k):
        r = await crear(*a, **k)
        uso["in"] += r.usage.input_tokens
        uso["out"] += r.usage.output_tokens
        uso["llamadas"] += 1
        return r
    cliente.messages.create = crear_contando

    juez = llm_factory(args.modelo, provider="anthropic", client=cliente, max_tokens=4000,
                       extra_body={"output_config": {"effort": args.esfuerzo}})
    juez.model_args.pop("temperature", None)
    juez.model_args.pop("top_p", None)
    print(f"judge: {args.modelo} ({args.esfuerzo}); arguments: {juez.model_args}")

    base = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    modelo_emb = os.getenv("LMSTUDIO_EMBED_MODEL", "text-embedding-bge-m3")
    emb = embedding_factory("openai", model=modelo_emb, client=AsyncOpenAI(base_url=base, api_key="lm-studio"))
    print(f"embeddings: {modelo_emb} en {base}")

    metricas = {"faithfulness": Faithfulness(llm=juez), "answer_relevancy": AnswerRelevancy(llm=juez, embeddings=emb),
                "context_recall": ContextRecall(llm=juez)}
    print("\n| Caso | faithfulness | answer_relevancy | context_recall | segundos |")
    print("|---|---|---|---|---|")
    for nombre, (ctx, resp) in CASOS.items():
        t0 = time.perf_counter()
        f = metricas["faithfulness"].score(user_input=PREGUNTA, response=resp, retrieved_contexts=ctx).value
        r = metricas["answer_relevancy"].score(user_input=PREGUNTA, response=resp).value
        c = metricas["context_recall"].score(user_input=PREGUNTA, retrieved_contexts=ctx, reference=REFERENCIA).value
        print(f"| {nombre} | {f:.2f} | {r:.2f} | {c:.2f} | {time.perf_counter() - t0:.1f} |")
    p = PRECIOS[f"anthropic:{args.modelo}"]
    print(f"\nJudge: {uso['llamadas']} calls, {uso['in']} input tokens and {uso['out']} output tokens; "
          f"cost ${(uso['in'] * p['in'] + uso['out'] * p['out']) / 1e6:.5f}")
    esperado = ("Esperado: fiel con faithfulness y relevance altas; cifra_cambiada con faithfulness baja; "
                "fuera_de_tema con relevance más baja que fiel; contexto_equivocado con context_recall baja.")
    print(esperado, file=sys.stderr)


if __name__ == "__main__":
    main()
