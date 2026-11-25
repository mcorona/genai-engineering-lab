# Activity 4: OCR of scanned documents

Run of 2026-10-26. Script: `experimentos/ocr.py`.

## Scans

5 documents, one page each, in `escaneos/`:

| Document | Origin | Purpose |
|---|---|---|
| `acta_inventario_norte` | `fuentes/` (frozen in activity 1) | 3 OCR questions of the gold set |
| `remision_r4471` | `fuentes/` (frozen in activity 1) | 2 OCR questions of the gold set |
| `devoluciones` | the week 8 corpus | passages `rec-01` to `rec-03` |
| `inventario_ciclico` | the week 8 corpus | passages `rec-04` to `rec-06` |
| `recepcion_almacen` | the week 8 corpus | passages `rec-18` to `rec-20` |

Process: Markdown → PDF (the activity 3 generator) → an image at 200 dpi in grayscale → random rotation of ±1.5°, Gaussian blur (0.6), Gaussian noise and salt-and-pepper dots → JPEG at quality 85. Fixed seed (20261026).

## Extractors

- **original (not scanned):** the visible text of the page; the upper reference.
- **Tesseract 5.5.3**, Spanish language (`spa`).
- **Claude Haiku 5.5** and **Claude Sonnet 5.5**, both with effort `low`, with the image as input and a transcription to Markdown.

The extractions are in `resultados/ocr_extracciones/`.

## Results

### Character error rate (CER)

| Extractor | Record | Delivery note | Returns | Cycle counting | Receiving | **Mean** |
|---|---|---|---|---|---|---|
| original (not scanned) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Tesseract (spa) | 0.003 | 0.007 | 0.016 | 0.017 | 0.004 | **0.009** |
| Claude Haiku 5.5 (low) | 0.003 | 0.000 | 0.000 | 0.000 | 0.000 | **0.001** |
| Claude Sonnet 5.5 (low) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | **0.000** |

### Retrieval (9 passages and 5 answers per language)

| Extractor | ES passages | EN passages | ES answers | EN answers |
|---|---|---|---|---|
| original (not scanned) | 8/9 | 8/9 | 5/5 | 5/5 |
| Tesseract (spa) | 8/9 | 8/9 | 5/5 | 5/5 |
| Claude Haiku 5.5 (low) | 8/9 | 8/9 | 5/5 | 5/5 |
| Claude Sonnet 5.5 (low) | 8/9 | 8/9 | 5/5 | 5/5 |

The passage that fails is `rec-06` (the ABC classes of cycle counting) with every extractor, including the original. It is a ranking problem of that question, not an OCR problem.

### Claude cost and latency

| Model | Input tokens | Output tokens | Cost (5 pages) | Cost per page | Mean latency |
|---|---|---|---|---|---|
| Haiku 5.5 (low) | 24,200 | 1,714 | $0.00328 | $0.0007 | 3.2 s |
| Sonnet 5.5 (low) | 24,200 | 1,714 | $0.06554 | $0.0131 | 4.3 s |

Each scanned page counts 4,840 input tokens (the image plus the prompt). Haiku and Sonnet transcribed **exactly the same text** in 4 of the 5 documents. In the inventory record, Haiku read a period as a parenthesis ("DIF)" instead of "DIF."); it is the only difference. That is why the output tokens match.

## Reading

- **Claude transcribes almost without errors:** Haiku, with a single wrong character in 5 pages; Sonnet, with none.
- **Tesseract has a CER of 0.9%, and most of it does not affect the content:** it reads the "•" bullets as "+" or "»", changes some punctuation ("Ficticia," for "Ficticia;") and makes the occasional letter error ("entrega" as "eritrega").
- **At this noise level, OCR does not change recall:** the 4 extractors retrieve the same as the original text, in passages and in answers. No Tesseract error fell inside a passage or a figure that was asked about.
- **Sonnet adds nothing over Haiku for this task:** the same text in 4 of 5 documents, at 20 times the cost and with more latency.

## Decision

- **Clean or moderately noisy scans, like these:** Tesseract. It costs nothing, runs locally and did not alter any figure or passage that was asked about.
- **When the accuracy of figures matters or the scan is poor** (inventory records, delivery notes, invoices): Claude Haiku 5.5 with effort `low`, at about $0.0007 per page.
- **Sonnet is not used for OCR:** it costs 20 times more and did not improve on Haiku.

## Limitations

- Synthetic scans with moderate noise, one page per document and a clean digital font. There is no handwriting, no stamps, stains, low resolution or phone photos.
- One document per source and a single noise seed. With more noise, the gap between Tesseract and Claude would probably grow; this run does not measure that.
- 9 passages and 5 answers per language.
- The CER counts bullet errors the same as content errors.
