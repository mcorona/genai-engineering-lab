# Week 11 RAG evaluation gold set (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 11 README](../README.md)

The frozen gold set of the week 11 RAG evaluation, and the script that built it. Each line is one question with its
gold passages and a reference answer. It joins three groups, 75 questions per language: the 50 base questions of
weeks 8 and 9, the 15 non-text questions of week 10 (answers only in a PDF, a scan or an image) and 10 new
unanswerable questions, whose answer is not in any document. A model (Haiku 5.5) wrote each reference answer from the
passage, or from the source document and the exact answer. Automatic checks ran on every answer, and a sample of 20
was reviewed by hand. The [week 11 README](../README.md) gives the size of each group, the checks and the
manual review ([`../resultados/revision_referencias.md`](../resultados/revision_referencias.md), with an English
gloss in [`../resultados/revision_referencias_en.md`](../resultados/revision_referencias_en.md)). Week 12 reuses this
set.

**Why it is in Spanish:** the lab measures RAG over a Spanish corpus. The gold passages must match the documents
word for word, and the Spanish reference answers are what the LLM judge compares against. Translating them would
change what was measured. The English file has English questions and English reference answers (some quote a
Spanish phrase from the passage), with the same Spanish gold passages.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `eval_rag_es.jsonl`, `eval_rag_en.jsonl` | The gold set, one JSON object per line | `construir_eval_rag.py`. Read by `../experimentos/suite_recuperacion.py`, `suite_generacion.py` and `meta_evaluacion.py`; the other week 11 experiments and `../ci/eval_ci.py` use it through them. Week 12 reads it too (`semana-12/evaluacion/suites.py`, `semana-12/ingesta/construir_paquete.py`) |
| `construir_eval_rag.py` | The builder: it joins the source sets, asks the model for each reference answer (cached in `../resultados/referencias_cache.json`) and runs the checks | Run when the set was frozen |

## Keys

| Key | Meaning |
|---|---|
| `id` | Question ID. Prefix: `rec` base (weeks 8 and 9), `int-pdf`, `int-ocr`, `int-imagen` non-text (week 10), `nr` unanswerable |
| `lang` | Language of the question and the reference answer (`es`, `en`) |
| `tipo` | Question type: `base`, `no_textual/pdf`, `no_textual/ocr`, `no_textual/imagen` (non-text, by medium), `sin_respuesta` (unanswerable) |
| `question` | The question |
| `gold` | Gold passages: a list of objects with `source` (the document) and `passage` (the exact Spanish text). For non-text questions, `passage` is the exact answer and `source` the week 10 source document. Empty for unanswerable questions |
| `referencia` | The reference answer. For unanswerable questions: the information is not in the documents |
| `respondible` | Answerable: `false` for unanswerable questions |
| `origen` | The set the question comes from: `semana-08/datasets/recuperacion`, `semana-10/datasets/integrado` or `semana-11` (new) |
