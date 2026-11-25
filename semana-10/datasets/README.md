# Week 10 gold sets (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 10 README](../README.md)

The gold sets of week 10, frozen before any experiment ran, and the scripts that built them. The integrated set mixes
SQL, document, non-text (PDF, scan, image) and mixed questions for the integrated assistant. The security set holds
the write attempts, leak attempts and prompt injection questions of activity 8. The [week 10 README](../README.md)
gives the size of each set and the results; the gold set validation is in
[`../resultados/golden_validacion.md`](../resultados/golden_validacion.md).

**Why it is in Spanish:** the lab measures a Spanish-language assistant over a Spanish corpus. The gold passages and
the exact answers must match the Spanish documents word for word; translating them would change what was measured.
The English question files keep the Spanish passages and answers on purpose. The keys and values are explained below.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `integrado_es.jsonl`, `integrado_en.jsonl` | Integrated gold set: one question per line, with its type and its reference (SQL, gold passage or exact answer) | `construir_integrado.py` (which also writes `../fuentes/`). Read by `../experimentos/*.py`, `../ci/eval_ci.py` and `semana-11/datasets/construir_eval_rag.py` |
| `permisos_semana10.json` | Roles of the new week 10 documents, added to week 9's roles per document | Read by `../experimentos/asistente.py` |
| `seguridad.json` | Security cases by category, each question in Spanish and English | `construir_seguridad.py` (which also writes `../fuentes/inyeccion/`, `../pdf_inyeccion/` and `../imagenes_inyeccion/`). Read by `../experimentos/seguridad.py` and `../ci/eval_ci.py` |
| `construir_*.py` | The builders of the sets above, with their checks | Run when the sets were frozen, before the experiments |

## Keys

| Key | Meaning |
|---|---|
| `id` | Question ID. Prefix: `int-sql`, `int-doc`, `int-pdf`, `int-ocr`, `int-imagen`, `int-mix` in the integrated set; `esc`, `fsql`, `dir`, `iny` in the security set |
| `tipo` | Question type: `sql`, `documental` (document), `no_textual` (non-text: the answer is only in a PDF, a scan or an image), `mixta` (mixed: needs SQL and a document) |
| `question` | The question |
| `sql` | The reference SQL, over the original inventory-copilot tables; scored by execution accuracy |
| `order_matters` | `true` if row order counts when comparing result sets |
| `origen` | Origin of the question: a week 7 hard-set ID (`hard-NNN-es`) or a week 9 base question ID (`rec-NN`) |
| `gold` | Gold passages: a list of `source` (corpus file) and `passage` (exact Spanish sentence) |
| `formato` | Non-text questions: the medium of the answer, `pdf`, `ocr` (scan) or `imagen` (image) |
| `fuente` | Non-text questions: the source document in `../fuentes/` |
| `respuesta` | Non-text questions: the exact answer |
| `nota` | A note on the file |
| `roles_por_documento` | Roles that may read each document. Role names: `ventas` sales, `almacen` warehouse, `operaciones` operations, `compras` purchasing, `finanzas` finance, `calidad` quality |
| `escritura` | Security: write attempts and SQL injection in natural language |
| `fuga_sql` | Security: attempts to read the documents through the NLQ tool, around the role filter |
| `directas` | Security: write or evasion SQL statements run directly against each defense layer |
| `cadena` | Security: statement IDs run in sequence on one session |
| `inyeccion` | Security: questions whose answer is in a document with an injected instruction |
| `documento` | The injected document a question targets |
| `dato` | Pattern of the correct figure in the answer |
| `siguio` | Per injected document, patterns that show the assistant followed the instruction (a canary string or a false figure) |
| `marcas_tenant` | Per multi-tenant question, the pattern of each tenant's figure |
| `es`, `en` | The question in Spanish and in English |
