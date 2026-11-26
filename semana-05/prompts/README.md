# Week 5 prompt library (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 5 README](../README.md)

The versioned prompt templates of week 5. Each template is a JSON file with its version, system prompt, user message
with `{variable}` placeholders, few-shot examples, optional tool definitions and an output-validation rule. Every
template points to the shared domain context in `_compartido/`, which `run_prompts.py` places first in the system
prompt so that it forms a cacheable prefix. Week 6's `evaluar.py` runs the same templates against its gold set, and
week 7's NLQ evaluation reuses the runner. The week README explains the structure and the validation rules in
[Structure](../README.md#structure).

**Why it is in Spanish:** the templates and the shared context are Spanish because they are the prompts being
measured, for a Spanish-language logistics assistant. Translating them would change what was measured. The keys and
the validation rules are explained below.

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `clasificacion_intencion.json` | Intent classification into a closed set of labels | Read by `run_prompts.py` and `semana-06/evaluar.py` |
| `extraccion_json.json` | Extraction of order data from a customer email into JSON | Read by `run_prompts.py` and `semana-06/evaluar.py` |
| `consulta_inventario.json` | Inventory query with tool use: the model calls `buscar_sku` | Read by `run_prompts.py` and `semana-06/evaluar.py` |
| `resumen_negocio.json` | Business summary in three bullets, with an `INSUFICIENTE` fallback when the input lacks the data | Read by `run_prompts.py` and `semana-06/evaluar.py` |
| `_compartido/contexto_logistica.md` | Shared domain context: the company and its operation (orders, inventory, quotations, complaints), the answer format, frequent terms, general rules and solved ambiguous cases | Read by `run_prompts.py` for every template |

## Keys

| Key | Meaning |
|---|---|
| `nombre` | Template name |
| `version` | Template version. It changes when the expected behavior changes |
| `descripcion` | What the template does |
| `contexto` | Path to the shared context, relative to this folder |
| `sistema` | System prompt |
| `usuario` | User message, with `{variable}` placeholders |
| `ejemplos` | Few-shot examples: `entrada` (input) and `salida` (expected output), sent as alternating user and assistant turns |
| `herramientas` | Tool definitions (name, description, JSON schema) |
| `validar` | Output validation: `"json"` (must parse as JSON), `etiquetas` (must be exactly one of the labels), or `resumen` (a set number of bullets of limited length, or the exact fallback answer) |
| `etiquetas` | The allowed labels: `consulta_pedido` (order status), `cotizacion` (request for a quotation), `queja` (complaint), `cancelacion` (cancellation), `otro` (other) |
| `vinetas`, `max_palabras`, `respuesta_exacta` | The summary rule: number of bullets, maximum words per bullet, and the exact fallback answer |
