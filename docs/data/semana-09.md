# Week 9 tenant beta corpus (Spanish data)

[Glossary](../glossary.md) · [Week 9 README](../../semana-09/README.md)

This page describes the week 9 data that sits outside a folder with its own README: the Spanish corpus of tenant
`beta` in `corpus_beta/`. The gold sets and the results have their own READMEs ([datasets](../../semana-09/datasets/README.md),
[resultados](../../semana-09/resultados/README.md)).

`corpus_beta/` holds 10 copies of documents from the week 8 corpus (`semana-08/corpus/`, tenant `alfa`). Each copy
differs from its original in one line: the value in the gold passage. In nine files it is a figure (a 20-day return
window instead of 30 days); in `ordenes_de_compra.md` it is the approver's title. The chunks of the two tenants are
therefore almost the same. The multi-tenant tests use this to check that a user of one tenant never receives the
other tenant's value.

`corpus_beta/` has no README of its own on purpose: the week 9 scripts, and scripts of weeks 10 and 12, load every
`*.md` file in that folder. A README there would join the corpus and change the measurements.

**Why it is in Spanish:** the lab measures RAG over Spanish documents, and these files must stay near-identical to the
Spanish week 8 originals. Translating them would change what was measured.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `corpus_beta/*.md` | Tenant `beta`'s documents: week 8 documents with one value changed | Written by `datasets/construir_multitenant.py`. Read by `experimentos/multitenant.py`, `ci/permisos_ci.py`, `semana-10/experimentos/seguridad.py` and `semana-12/ingesta/construir_paquete.py` |
