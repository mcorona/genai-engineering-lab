# Activity 5: images

Run of 2026-10-26. Script: `experimentos/imagenes.py`. Model: **claude-haiku-5-5, effort `low`**.

## Images

Generated with Pillow from the sources frozen in activity 1 and checked by eye before the run (`imagenes/`):

- **`grafica_nivel_servicio.png`**: bars of the service level per distribution center in September 2026, with the value above each bar and the center's name below it (Centro 97.8%, Occidente 95.1%, Norte 98.6%).
- **`plano_cedis_occidente.png`**: receiving docks 1 to 4 and shipping docks 5 to 8, the critical-SKU zone below dock 2, and the quarantine zone inside aisle 12.

In both, the answer requires **associating** elements by their position: a value with its bar, or a zone with its dock or aisle. During the review, two ambiguities in the drawings were fixed before the run: the quarantine label spilled into aisle 13, and the critical-SKU zone spanned docks 2 and 3.

## Uses of the image

- **no image:** only the text corpus (the baseline).
- **Tesseract (spa):** OCR of the image.
- **Claude, description:** Haiku describes the image and extracts its data, one line per fact; that text is indexed with the pipeline.
- **Claude, direct answer:** Haiku answers the question by looking at the image, without RAG.

## Results

| Use of the image | Facts extracted (label and value on the same line) | ES recall@5 | EN recall@5 | ES direct answer | EN direct answer |
|---|---|---|---|---|---|
| no image | 0/7 | 0/5 | 0/5 | - | - |
| Tesseract (spa) | **0/7** | 4/5 | 4/5 | - | - |
| Claude Haiku 5.5 (low), description | **7/7** | **5/5** | **5/5** | - | - |
| Claude Haiku 5.5 (low), direct answer | - | - | - | **5/5** | **5/5** |

**Claude cost:** $0.00295 for 12 calls (2 descriptions and 10 direct answers), with 18,944 input tokens and 2,099 output tokens. Mean latency of 1.8 s.

Detail: `imagenes_detalle.csv`. Extractions: `imagenes_extracciones/`.

## Reading

- **Tesseract reads the labels but not the relations.** In the chart, it mixes the values with the axis ticks ("08% 7 97.8%"), puts the three center names on a separate line and **did not read "98.6%"**. In the floor plan, it lists the labels by rows ("Andén 1 … Andén 8", "Zona de SKUs" / "críticos", "Pasillo 10 … Pasillo 14") without saying which zone is next to which dock or in which aisle. It associated 0 of 7 facts.
- **The 4/5 recall@5 overstates Tesseract.** The metric counts as a hit a chunk that contains the answer's figure or label, even when it is disconnected from its label. The only miss is the Norte center question, because "98.6%" was not read. That is why this activity also measures associated facts.
- **Haiku extracts all 7 facts with their relation** ("CEDIS Occidente: 95.1%", "Zona de SKUs críticos: … debajo del Andén 2", "Zona de cuarentena: … del Pasillo 12"), and its description retrieves all 10 questions.
- **The direct answer is also right on 10 of 10.** In English it copied the labels as they appear in the image ("Pasillo 12", "Andén 2"), as the prompt asks.

## Decision

**Images with data (charts, floor plans, diagrams): Haiku 5.5 `low` describes them and extracts the data at indexing time**, at between $0.0003 and $0.0006 per image (a mean of $0.00047 in this run). The description goes into the same index as the rest of the corpus, so the assistant can retrieve and cite it. Tesseract does not work for images whose meaning depends on position. The direct answer over the image is just as accurate, but it requires knowing in advance which image to look at; in the assistant, the image is found through its indexed description.

## Limitations

- Two synthetic, clean images with legible labels. There are no photos, scanned diagrams or charts without value labels (where the value would have to be estimated from the bar height).
- 5 questions per language and 7 facts.
- The facts metric looks for the label and the value on the same line: it approximates "correct association"; it is not a semantic check.
- One run, with a single model and effort level.
