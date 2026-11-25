# Week 10 PDFs with tables (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 10 README](../README.md)

The PDFs of activity 3 (tables in PDFs). The script renders four Spanish Markdown documents with tables or lists to
PDF, then compares how each extractor recovers the table rows. The results are in
[`../resultados/pdf_tablas.md`](../resultados/pdf_tablas.md).

- `tarifas_flete.pdf`: freight rates between distribution centers (route, rate in MXN, transit time). Source:
  `../fuentes/tarifas_flete.md`.
- `matriz_proveedores.pdf`: supplier matrix by category (supplier, country, category, rating, agreed lead time).
  Source: `../fuentes/matriz_proveedores.md`.
- `ordenes_de_compra.pdf`, `proveedores.pdf`: the purchase order policy (with its approval-level table) and the
  supplier document (with lead times), from the week 8 corpus.

The first two hold answers that exist only in these PDFs, never in the text corpus.

**Why it is in Spanish:** the lab measures extraction and RAG on Spanish business documents. The extracted cells are
matched against the Spanish original; translating the documents would change what was measured.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `*.pdf` | The four rendered documents | Written by `../experimentos/pdf_tablas.py`. Read by `../experimentos/pdf_tablas.py` and `../ci/eval_ci.py` |
