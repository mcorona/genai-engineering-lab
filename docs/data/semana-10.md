# Week 10 source documents (Spanish data)

[Glossary](../glossary.md) · [Week 10 README](../../semana-10/README.md)

This page describes the week 10 data that sits outside a folder with its own README: the frozen source documents in
`fuentes/` and `fuentes/inyeccion/`. The other data folders have their own READMEs: [datasets](../../semana-10/datasets/README.md),
[escaneos](../../semana-10/escaneos/README.md), [imagenes](../../semana-10/imagenes/README.md), [imagenes_inyeccion](../../semana-10/imagenes_inyeccion/README.md),
[legado](../../semana-10/legado/README.md), [pdf](../../semana-10/pdf/README.md), [pdf_inyeccion](../../semana-10/pdf_inyeccion/README.md) and
[resultados](../../semana-10/resultados/README.md).

`fuentes/` holds the content of the non-text documents before they become a PDF, a scan or an image. Their answers
exist only in these documents, never in the week 8 text corpus, so the assistant can find them only by reading the
PDF, the scan or the image. The scripts of activities 3 to 5 turn each source into its medium without changing its
content. `fuentes/inyeccion/` holds the sources of the security test documents, each with an injected instruction.

`fuentes/` has no README of its own on purpose: week 11's gold set builder reads every file at the top level of that
folder (`fuentes/*.*`). A README there would join its corpus check and change the build. `fuentes/inyeccion/` is
described here too, with the rest of `fuentes/`.

**Why it is in Spanish:** the documents belong to the fictional Mexican distributor that the lab measures. The gold
set's exact answers must match them word for word, and the injected text is part of each attack case. Translating
them would change what was measured.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `fuentes/*.md` | Source documents in Markdown: freight rates and the supplier matrix (rendered to PDF), a physical inventory record and a delivery note (scanned) | Written by `datasets/construir_integrado.py`. Read by `experimentos/pdf_tablas.py`, `experimentos/ocr.py`, `ci/eval_ci.py` and `semana-11/datasets/construir_eval_rag.py` |
| `fuentes/*.json` | Image specs: the service-level chart and the floor plan of CEDIS Occidente, drawn into `imagenes/` | Written by `datasets/construir_integrado.py`. Read by `experimentos/imagenes.py` and `semana-11/datasets/construir_eval_rag.py` |
| `fuentes/inyeccion/*.md` | Sources of the two PDFs with injected instructions in `pdf_inyeccion/` (travel expense caps, equipment warranties) | Written by `datasets/construir_seguridad.py`. Read by `experimentos/seguridad.py` |
| `fuentes/inyeccion/*.json` | Specs of the two images with injected instructions in `imagenes_inyeccion/`, with the injected text | Written by `datasets/construir_seguridad.py`. Read by `experimentos/seguridad.py` |

## Keys

| Key | Meaning |
|---|---|
| `tipo` | Kind of image: `gráfica de barras` (bar chart) or `plano` (floor plan) |
| `titulo` | Title shown on the image |
| `barras` | Bar chart values: label → value |
| `zonas` | Floor plan zones and docks, as Spanish sentences |
| `filas` | Table rows shown on the image |
| `inyeccion` | The injected instruction drawn on the image |
| `nota` | Footer note: a synthetic document of a fictional company |
