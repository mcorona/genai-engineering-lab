# Week 6 judge rubric (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 6 README](../README.md)

The rubric of the LLM judge that scores the faithfulness of the summaries. `evaluar.py` fills the `{documento}` and
`{resumen}` placeholders with the source document and the summary, and sends it for the gold-set cases marked
`juez: true` ([`../golden/`](../golden/README.md)), once the summary passes its structural check. The judge answers with JSON: a faithfulness score on a 1-to-5
scale and a short reason. A summary passes with a score of 4 or 5.

**Why it is in Spanish:** the documents and the summaries are Spanish, and the judge is instructed in the same
language as the content it scores. Translating the rubric would change the judge that was measured.

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `fidelidad_resumen.txt` | The faithfulness rubric: the scale, the anchors for scores 5, 3 and 1, and the JSON output format | Read by `evaluar.py` |

## Keys

| Key | Meaning |
|---|---|
| `fidelidad` | The faithfulness score the judge must return, an integer from 1 to 5 |
| `motivo` | The judge's reason, at most 25 words |
| `documento`, `resumen` | Placeholders for the source document and the summary to score |
