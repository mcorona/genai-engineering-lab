"""Week 12, activity 8: the final table of option × ingestion mode × language with recall@5, nDCG@10, faithfulness, answer
relevance, accuracy, leaks, latency and cost, built from the summaries of activities 3 to 7 (no API calls).
Writes resultados/comparacion_tabla.md and resultados/comparacion.json.
"""
import json
from pathlib import Path

RES = Path(__file__).resolve().parents[1] / "resultados"
J = lambda n: json.loads((RES / f"{n}_resumen.json").read_text(encoding="utf-8"))  # noqa: E731
LAT, COS, SEG = J("latencia"), J("costos"), J("seguridad")
PROPIO_GEN = J("propio")["costo_usd_por_consulta"]["generacion"]
RANKING = COS["precios"]["ranking"]

# (summary name, option, ingestion mode, generator, system in the security results, key in latency, key in costs)
FILAS = [
    ("propio", "Own pipeline (pgvector + Haiku reranking)", "own chunks", "common", None, "propio", "propio"),
    ("bedrock_adm-pred", "Bedrock KB, Retrieve", "managed: default chunking/parser", "common", "bedrock adm-pred", None, None),
    ("bedrock_adm-fijo", "Bedrock KB, Retrieve", "managed: fixed 100 tok / 20%", "common", "bedrock adm-fijo", None, None),
    ("bedrock_adm-fijo-bda", "Bedrock KB, Retrieve", "managed: fixed + BDA multimodal", "common", "bedrock adm-fijo-bda", None, None),
    ("bedrock_ctl-chunks", "Bedrock KB, Retrieve", "controlled: own chunks", "common", "bedrock ctl-chunks", "bedrock_ctl", "bedrock_ctl-chunks"),
    ("bedrock_adm-pred_rag", "Bedrock RetrieveAndGenerate", "managed: default chunking/parser", "Haiku 4.5 (Bedrock)", None, None, None),
    ("bedrock_adm-fijo-bda_rag", "Bedrock RetrieveAndGenerate", "managed: fixed + BDA multimodal", "Haiku 4.5 (Bedrock)",
     "bedrock adm-fijo-bda RetrieveAndGenerate", "bedrock_bda_rag", "bedrock_adm-fijo-bda"),
    ("bedrock_ctl-chunks_rag", "Bedrock RetrieveAndGenerate", "controlled: own chunks", "Haiku 4.5 (Bedrock)", None, None, None),
    ("vertex_vx-adm_hibrida", "Vertex AI Search, hybrid", "managed: layout parser", "common", "vertex vx-adm", None, None),
    ("vertex_vx-adm_vectorial", "Vertex AI Search, vector", "managed: layout parser", "common", "vertex vx-adm", None, None),
    ("vertex_vx-adm_semantico", "Vertex AI Search, semantic ranker", "managed: layout parser", "common", "vertex vx-adm",
     "vertex_adm_sem", "vertex_vx-adm"),
    ("vertex_vx-ctl_hibrida", "Vertex AI Search, hybrid", "controlled: own chunks", "common", "vertex vx-ctl", None, None),
    ("vertex_vx-ctl_vectorial", "Vertex AI Search, vector", "controlled: own chunks", "common", "vertex vx-ctl", None, None),
    ("vertex_vx-ctl_semantico", "Vertex AI Search, semantic ranker", "controlled: own chunks", "common", "vertex vx-ctl",
     "vertex_ctl_sem", "vertex_vx-ctl"),
]


def main():
    filas = []
    for res, opcion, modo, gen, seg, lat, cos in FILAS:
        r = J(res)
        if seg:
            s = SEG["sistemas"][seg]
            fuga = f"{s['rol']['chunks_no_autorizados'] + s['tenant']['chunks_no_autorizados']} / {s['rol']['consultas'] + s['tenant']['consultas']}"
        elif res == "propio":
            fuga = "0 (weeks 9-10)"
        else:
            fuga = "same filter as Retrieve"
        if lat:
            latencia = f"{LAT[lat]['total_p50']} / {LAT[lat]['total_p95']}"
        else:
            latencia = f"ret. {r['latencia_s']['recuperacion']['p50']}*"
        if cos:
            costo = COS["variable_por_consulta_usd"][cos]
        else:
            c = r["costo_usd_por_consulta"]
            costo = c["recuperacion"] + c["generacion"] + (RANKING if "semantico" in res else 0)
        costo_txt = f"{costo:.5f}" + (" + search past 10k/mo" if res.startswith("vertex") else "") + (" (est.)" if "_rag" in res else "")
        for lang in ("es", "en"):
            rec, g = r["recuperacion"][lang], r["generacion"][lang]
            filas.append({"option": opcion, "ingestion": modo, "generator": gen, "lang": lang.upper(),
                          "recall@5": rec["recall@5"], "ndcg@10": rec["ndcg@10"], "mrr": rec["mrr"], "doc_recall@5": rec["doc_recall@5"],
                          "faithfulness": g["faithfulness"], "answer_relevancy": g["answer_relevancy"], "correctness": g["exactitud"],
                          "correct_abstention": g["abstencion_correcta"], "leakage": fuga, "latency_s": latencia, "usd_per_query": costo_txt})
    (RES / "comparacion.json").write_text(json.dumps(filas, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    cab = ["Option", "Ingestion mode", "Generator", "Lang", "recall@5", "nDCG@10", "faithfulness", "answer relevancy",
           "Correctness", "Correct abstention", "Leakage (chunks / queries)", "Latency p50 / p95 (s)", "USD per query"]
    lineas = ["| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
    for f in filas:
        lineas.append("| " + " | ".join([f["option"], f["ingestion"], f["generator"], f["lang"], f"{f['recall@5']:.3f}", f"{f['ndcg@10']:.3f}",
                                          f"{f['faithfulness']:.3f}", f"{f['answer_relevancy']:.3f}", f"{f['correctness']:.3f}",
                                          f["correct_abstention"], f["leakage"], f["latency_s"], f["usd_per_query"]]) + " |")
    (RES / "comparacion_tabla.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))


if __name__ == "__main__":
    main()
