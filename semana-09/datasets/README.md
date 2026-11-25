# Week 9 gold sets (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 9 README](../README.md)

The gold sets of the week 9 advanced RAG experiments, frozen before any experiment ran, and the scripts that built
them. Each JSONL line is one question with its gold passages: exact sentences from the week 8 corpus
(`semana-08/corpus/`) or from the tenant `beta` corpus (`../corpus_beta/`). The English files hold the same questions
in English with the same Spanish gold passages. The [week 9 README](../README.md) lists each set, its size and its
purpose; the [DATA.md](../DATA.md) describes `corpus_beta/`.

**Why it is in Spanish:** the corpus is Spanish, and the gold passages must match it word for word. The lab measures
RAG over Spanish documents; translating the data would change what was measured. The keys and values are explained
below.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `avanzado_es.jsonl`, `avanzado_en.jsonl` | Main set: the week 8 base questions, plus follow-up questions and permission questions | `construir_golden.py`. Read by `../experimentos/reescritura.py`, `hyde.py`, `contextual.py`, `permisos.py`, `multitenant.py` and `../ci/permisos_ci.py` |
| `permisos.json` | The synthetic access model: which roles may read each corpus document | `construir_golden.py`. Read by `../experimentos/permisos.py` and `../ci/permisos_ci.py` |
| `multitenant_es.jsonl`, `multitenant_en.jsonl` | Multi-tenant set: near-identical documents in tenants `alfa` and `beta`, with a different figure in each | `construir_multitenant.py` (which also writes `../corpus_beta/`). Read by `../experimentos/multitenant.py`, `../ci/permisos_ci.py` and week 10's security tests |
| `multisalto_es.jsonl`, `multisalto_en.jsonl` | Multi-hop, compound: two documents per question, both topics named in the question (the control) | `construir_multisalto.py`. Read by `../experimentos/graphrag.py` |
| `multisalto_puente_es.jsonl`, `multisalto_puente_en.jsonl` | Multi-hop, bridge: two documents per question, the entity that links them is not named (the best case for GraphRAG) | `construir_multisalto.py`. Read by `../experimentos/graphrag.py` |
| `construir_*.py` | The builders of the sets above, with their checks on the gold passages | Run when the sets were frozen, before the experiments |

## Keys

| Key | Meaning |
|---|---|
| `id` | Question ID. Prefix: `rec` base (from week 8), `seg` follow-up, `perm` permission, `mt-rec` multi-tenant, `ms` compound multi-hop, `pt` bridge multi-hop |
| `lang` | Language of the question (`es`, `en`) |
| `tipo` | Question type: `base`, `seguimiento` (follow-up), `permiso` (permission) |
| `question` | The question |
| `pregunta_previa` | Follow-up questions only: the previous question in the conversation, which the follow-up depends on |
| `usuario` | Permission questions only: the user who asks, as `tenant` and `roles` |
| `permitido` | Permission questions only: `true` if the user's roles may read the gold document |
| `gold` | The gold passages: a list of `source` (corpus file) and `passage` (exact Spanish sentence). In the multi-tenant set, an object with tenant `alfa`'s passage and tenant `beta`'s |
| `set` | Multi-hop sets: `compuestas` (compound) or `puente` (bridge) |
| `base` | Compound multi-hop only: the IDs of the two base questions whose passages it combines |
| `source` | The corpus file name (in `gold`, or at the top level in the multi-tenant set) |
| `tenants` | `permisos.json`: the tenants and a note on each |
| `roles_por_documento` | `permisos.json`: roles per document. Role names: `ventas` sales, `almacen` warehouse, `operaciones` operations, `compras` purchasing, `finanzas` finance, `calidad` quality |
| `nota` | `permisos.json`: a note that the access model is synthetic, not the real permissions of inventory-copilot |
