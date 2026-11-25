# Week 10 scanned pages (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 10 README](../README.md)

The scanned pages of activity 4 (OCR). Each JPEG is the first page of a Spanish document, rendered to PDF, then to a
grayscale image with a slight rotation, blur and noise from a fixed seed, so it looks like a scan. Two pages come
from the week 10 sources (`../fuentes/acta_inventario_norte.md`, a physical inventory record of CEDIS Norte, and
`../fuentes/remision_r4471.md`, a supplier delivery note); three come from dense-text documents of the week 8
corpus (returns, cycle counts, warehouse receiving). Their answers are not in the text corpus, so the assistant can
only find them by reading the scan. The OCR results are in [`../resultados/ocr.md`](../resultados/ocr.md).

**Why it is in Spanish:** the lab measures OCR and RAG on Spanish business documents. The extracted text is scored
against the Spanish original, character by character; a translated page would measure something else.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `*_p1.jpg` | Page 1 of each scanned document; the name is the source document's | Written by `../experimentos/ocr.py`. Read by `../experimentos/ocr.py`, `../ci/eval_ci.py` and `semana-12/ingesta/construir_paquete.py` |
