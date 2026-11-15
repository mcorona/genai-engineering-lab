# Activity 3: PDFs with tables

Run of 2026-10-26. Script: `experimentos/pdf_tablas.py`.

## PDFs

Generated with reportlab (Arial Unicode font, to keep "→" and accents) in `pdf/`:

| PDF | Origin | Reference table |
|---|---|---|
| `tarifas_flete.pdf` | `fuentes/tarifas_flete.md` (the source frozen in activity 1) | 4 rows × 3 columns |
| `matriz_proveedores.pdf` | `fuentes/matriz_proveedores.md` (the source frozen in activity 1) | 5 rows × 5 columns |
| `ordenes_de_compra.pdf` | `semana-08/corpus/ordenes_de_compra.md` (approval levels) | 4 rows × 2 columns |
| `proveedores.pdf` | `semana-08/corpus/proveedores.md` (lead times, as a list) | no table; it only counts for recall |

Reference total: 3 tables, 13 rows, 45 cells.

## Extractors

- **original (no PDF):** the source Markdown; the upper reference.
- **pypdf:** the plain text of each page.
- **pdfplumber:** tables detected as rows (`cell | cell | …`) and the rest of the text separately.
- **Claude Haiku 5.5, effort `low`:** the PDF as input, transcribed to Markdown. Cost: **$0.00162** for the 4 PDFs (8,148 input tokens and 1,615 output tokens), 2.5 s on average per PDF.

The extractions are in `resultados/pdf_extracciones/`.

## Results

### Table structure

| Extractor | Cells present | Cells in their row | Intact rows |
|---|---|---|---|
| original (no PDF) | 45/45 (1.000) | 45/45 (1.000) | 13/13 |
| pypdf | 45/45 (1.000) | 14/45 (0.311) | **0/13** |
| pdfplumber | 45/45 (1.000) | **45/45 (1.000)** | **13/13** |
| Claude Haiku 5.5 (low) | 45/45 (1.000) | **45/45 (1.000)** | **13/13** |

### Retrieval (the gold set's PDF questions, 5 per language)

| Extractor | ES recall@5 | EN recall@5 |
|---|---|---|
| original (no PDF) | 4/5 | 4/5 |
| pypdf | 5/5 | 5/5 |
| pdfplumber | 5/5 | 4/5 |
| Claude Haiku 5.5 (low) | 4/5 | 5/5 |

Every miss is the same question, `int-pdf-05` ("which supplier in the Seguridad (safety) category has a C rating?"). The word "Seguridad" attracts corpus chunks about that category (returns, discounts, facility security), and the matrix chunk falls outside the top 5 depending on how it was cut. It fails even with the original text, so it is a ranking problem, not an extraction problem.

## Reading

- **All three extractors keep the text:** the 45 cells appear in all of them.
- **pypdf loses the table structure:** it leaves each cell on its own line (for example, "Guadalajara → Monterrey", then "$10,900", then "2 días"), so no row stays intact. Answering "how much does route X cost" requires reconstructing which value goes with which route from the order of the text, which is fragile for wide or multi-page tables.
- **pdfplumber and Claude keep all 13 rows complete.** pdfplumber does it for free, locally and deterministically; Claude costs about $0.0004 per page and takes about 2.5 s.
- **recall@5 does not separate the extractors on this set:** the answers are single cells that appear in the chunk even when the row is broken, and the only difference is a ranking question. The effect of structure on the final answer is measured in activity 7, with the assistant.

## Decision

**pdfplumber** as the default extractor for digital PDFs with tables: the same structure as Claude, with no cost and no external calls. Claude is kept for what pdfplumber does not cover: scanned PDFs (activity 4) or tables with merged cells and complex structures. pypdf is not used for documents with tables.

## Limitations

- PDFs generated with reportlab, clean and one page long, with simple grid tables. Real PDFs (merged cells, borderless tables, multiple pages) are harder for pdfplumber.
- 5 questions per language: one question moves recall by 0.2.
- pdfplumber appends the tables at the end of the page text, not at their original position, which can separate a table from its heading when chunking.
- One Claude run, with a single model and effort level.
