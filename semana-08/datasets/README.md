# Week 8 retrieval gold set (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 8 README](../README.md)

The questions that every week 8 retrieval experiment runs against the Spanish corpus in `../corpus/`. Each line is
one question with its gold passages: exact sentences copied from a corpus document. A retrieved chunk counts as a hit
when it contains a gold passage verbatim, so the metric does not depend on how the text is split. The English file
holds the same questions, translated, with the same Spanish gold passages, so it measures cross-lingual retrieval
(English question, Spanish corpus). The week 8 README gives the question count and the results. Later weeks build on
this set (`semana-09/datasets/construir_golden.py`, `semana-11/datasets/construir_eval_rag.py`).

**Why it is in Spanish:** the corpus is Spanish, and the lab measures retrieval over Spanish documents. The gold
passages must match the corpus word for word, so they cannot be translated. The Spanish questions are the primary
set; the English questions are part of the experiment, not a translation for the reader.

## Files

| File(s) | What it is | Read by |
|---|---|---|
| `recuperacion_es.jsonl` | Gold set, Spanish questions, one JSON object per line | `experimentos/*.py` (chunking, embeddings, vector databases, hybrid search, reranking, end to end) and `ci/recuperacion_ci.py` |
| `recuperacion_en.jsonl` | The same questions in English, with the same Spanish gold passages | Same scripts, except `experimentos/chunking_pasajes.py`, which reads only the Spanish file |

## Keys

| Key | Meaning |
|---|---|
| `id` | Question ID (`rec-NN`); the same ID in both languages |
| `lang` | Language of the question (`es`, `en`) |
| `question` | The question |
| `gold` | The gold passages: a list of `source` (corpus file name) and `passage` (the exact Spanish sentence) |
