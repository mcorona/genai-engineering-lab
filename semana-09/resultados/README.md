# Week 9 results (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 9 README](../README.md)

The results of the week 9 advanced RAG experiments: query rewriting, HyDE, contextual retrieval, role filters,
multi-tenant isolation, GraphRAG and the CI eval. Each technique has an English report (`*.md`) that names its script
and its run. The raw files next to the reports hold the per-question detail and the model outputs that the scripts
cache and reuse.

**Recorded evidence:** the CSV and JSONL files are the raw outputs of the runs, kept exactly as recorded (not edited,
not translated). They were written by the scripts in `../experimentos/` named below. Their Spanish text (questions,
rewritten queries, generated passages, chunk contexts, graph entities) is model input or output in Spanish. The English
summary of the results is in the [week 9 README](../README.md) and in the reports, starting with
[`comparacion_final.md`](comparacion_final.md).

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `*.md` | English reports, one per activity, plus the final comparison ([`comparacion_final.md`](comparacion_final.md)) and the CI run ([`ci_semana09.md`](ci_semana09.md), from `../ci/permisos_ci.py`) | Written from the runs of the scripts each one names |
| `reescritura_detalle.csv` | Query rewriting: one row per question, with the original and the rewritten query and their hits | `../experimentos/reescritura.py` |
| `hyde_detalle.csv` | HyDE: one row per question, with the generated hypothetical passage and the hits with and without it | `../experimentos/hyde.py` |
| `contextos.jsonl` | Contextual retrieval: the context the model wrote for each chunk, cached and reused | Written and read by `../experimentos/contextual.py` |
| `contextual_detalle.csv` | Contextual retrieval: one row per question, hits of the baseline index and of the contextual index | `../experimentos/contextual.py` |
| `grafo_extraccion.jsonl` | GraphRAG: the entities and relations the model extracted from each chunk, cached and reused | Written and read by `../experimentos/graphrag.py` |
| `graphrag_detalle.csv` | GraphRAG: one row per multi-hop question, recall@5 of each retrieval method | `../experimentos/graphrag.py` |

## Keys

| Key | Meaning |
|---|---|
| `tipo` | Question type: `base`, `seguimiento` (follow-up) |
| `idioma` | Language (`es`, `en`) |
| `pregunta` | The question |
| `previa` | The previous question, for follow-up questions |
| `reescrita` | The rewritten, standalone query |
| `pasaje_hyde` | The hypothetical passage generated for HyDE |
| `acierto_original_r5`, `acierto_reescrita_r5`, `acierto_hyde_r5` | Hit at 5 (`1` if a gold passage is in the top 5) with the original question, the rewritten query, the HyDE passage |
| `acierto_base_r5`, `acierto_contextual_r5` | Hit at 5 with the baseline index and with the contextual index |
| `tipos_bloque` | The content block types the model returned, joined with `\|` (`text`, `thinking\|text`) |
| `latencia_ms` | Latency in milliseconds |
| `costo_usd` | Cost of the model call, in USD |
| `set` | Multi-hop set: `compuestas` (compound) or `puente` (bridge) |
| `entidades_pregunta`, `entidades_en_grafo` | The entities the model extracted from the question; the graph entities they matched |
| `recall5_V`, `recall5_V+R`, `recall5_G`, `recall5_G+Q` | recall@5 per method (the share of the question's two gold passages in the top 5): `V` vector, `V+R` vector + reranking, `G` graph expansion from vector seeds, `G+Q` graph lookup of the question's entities fused with vector results |
| `huella` | Fingerprint of the chunk (a hash of source, position and text), the cache key |
| `contexto` | The context sentence the model wrote for the chunk |
| `ok` | `true` if the model returned valid JSON for the chunk |
| `entidades` | Extracted entities, each with `nombre` (name) and `tipo` (type) |
| `relaciones` | Extracted relations, each with `origen` (source entity), `relacion` (relation) and `destino` (target entity) |
