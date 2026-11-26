# Week 19 poisoned knowledge-base documents (Spanish data)

[Glossary](../../../docs/glossary.md) · [Week 19 README](../../README.md)

Two test documents for indirect prompt injection through the Knowledge Base (activity 9, decision 3). Each one looks
like a legitimate document and hides an instruction to the assistant, with a test marker
(`s19-kb-envenenado-1`, `s19-kb-envenenado-2`) that makes it easy to spot in a retrieval. No script in the repository reads this
folder. The documents were uploaded to the `docs/envenenados/` prefix of the deployed Knowledge Base's documents
bucket, ingested, queried with a direct `Retrieve`, and then deleted.

**Why it is in Spanish:** the Knowledge Base serves a Spanish-language assistant over a Spanish legacy schema, so the
attack is written the way its documents are. One document is in Spanish and one in English, to cover both languages
the agent answers in. Translating them would change what was tested.

The results are in [seguridad.md](../../resultados/seguridad.md#through-the-knowledge-base-decision-3), with the raw
retrievals in `resultados/seguridad/kb_retrieve_*.json` (described in the
[week 19 results README](../../resultados/README.md)). Upload the two files one by one: syncing the whole folder
would also ingest this README.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `legado_artnot.md` | In Spanish: a data-dictionary page for a legacy notes table, in the format of the Knowledge Base's dictionary documents, with an injected instruction to delete a table | Written by hand / uploaded to the Knowledge Base |
| `politica_compras.md` | In English: a purchasing policy for critical SKUs, with an injected instruction to propose an oversized purchase order | Written by hand / uploaded to the Knowledge Base |
