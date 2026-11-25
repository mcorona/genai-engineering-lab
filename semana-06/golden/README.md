# Week 6 gold set (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 6 README](../README.md)

The cases that `evaluar.py` runs against the week 5 prompt templates. Each line is one case: which template to fill,
the values to fill it with, which check to apply and the expected answer. The week 6 README gives the case count and
the results.

**Why it is in Spanish:** the prompts, the customer messages and the expected labels are Spanish, because the lab
measures a Spanish-language assistant. Translating them would change what was measured. The keys and labels are
explained below.

## Files

| File | What it is | Read by |
|---|---|---|
| `casos.jsonl` | The gold-set cases, one JSON object per line | `evaluar.py` |

## Keys

| Key | Meaning |
|---|---|
| `id` | Case ID. The prefix names the task: `clas` classification, `ext` extraction, `con` inventory query (tool use), `res` summary |
| `plantilla` | The week 5 prompt template to fill (`semana-05/prompts/<plantilla>.json`) |
| `variables` | The values that fill the template: `mensaje` (customer message), `pregunta` (question) |
| `mensaje` | A customer message, in Spanish |
| `pregunta` | A question, in Spanish |
| `check` | How the answer is scored: `etiqueta` (label match), `json_campos` (JSON fields), `herramienta` (tool call), `resumen_estructura` (summary structure) |
| `esperado` | The expected answer: a label such as `consulta_pedido` (order status), `cotizacion` (quote request), `queja` (complaint) or `otro` (other) |
| `juez` | `true` when an LLM judge also scores the answer for faithfulness, with the rubric in `../rubricas/` |
