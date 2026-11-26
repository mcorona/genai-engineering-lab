# Week 6 gold set (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 6 README](../README.md)

The cases that `evaluar.py` runs against the week 5 prompt templates. Each line is one case: which template to fill,
the values to fill it with, which check to apply and the expected answer. There are 16 cases: 6 classification,
4 extraction, 3 tool use and 3 summary. The week 6 README describes the checks and the results.

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
| `variables` | The values that fill the template: `mensaje`, `correo`, `pregunta` or `documento`, by template |
| `mensaje` | A customer message to classify, in Spanish |
| `correo` | A customer email to extract order data from, in Spanish |
| `pregunta` | An inventory question, in Spanish |
| `documento` | A business document to summarize, in Spanish |
| `check` | How the answer is scored: `etiqueta` (the output is exactly the expected text), `json_campos` (the output is valid JSON and the listed fields match), `herramienta` (the expected tool call, or no call), `resumen_estructura` (three bullets of at most 25 words, or `INSUFICIENTE`) |
| `esperado` | The expected answer. For `etiqueta`: a label, `consulta_pedido` (order status), `cotizacion` (quotation request), `queja` (complaint), `cancelacion` (cancellation) or `otro` (other), or the fallback `INSUFICIENTE`. For `json_campos`: the fields to compare. For `herramienta`: the tool call (`nombre`, `entrada`), or `null` when no tool must be called. Absent for `resumen_estructura` |
| `juez` | `true` when an LLM judge also scores the summary for faithfulness, with the rubric in `../rubricas/`, after the structural check passes |
