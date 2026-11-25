# Week 5: multi-model prompting and a versioned prompt library

> Spanish names (folders, files, JSON keys, flags, stack names, status values) are explained in the [glossary](../docs/glossary.md). The documentation is in English.

Goal: treat every prompt as code. Each template lives in Git with a version, few-shot examples, a validatable output format and a reproducible command to run it.

## Structure

| File | Contents |
|---|---|
| `prompts/resumen_negocio.json` | Fixed-format output (three bullets) with an `INSUFICIENTE` fallback rule |
| `prompts/extraccion_json.json` | Extraction to valid JSON, with one few-shot example and validation with `json.loads` |
| `prompts/clasificacion_intencion.json` | Classification into a closed set of labels, with two few-shot examples and validation against the list |
| `prompts/consulta_inventario.json` | Basic tool use: the model decides to call `buscar_sku` with a JSON schema |
| `prompts/_compartido/contexto_logistica.md` | Shared domain context (glossary, rules, solved cases). It is prepended to the system prompt of each template; it is the stable part that gets cached |
| `run_prompts.py` | A runner with no external dependencies (Python standard library only) |
| `resultados/ejecuciones.jsonl` | A log of each execution: template version, model, latency, tokens, validation and output |

Each template is a JSON file with `nombre`, `version`, `contexto` (the path to the shared context), `sistema`, `usuario` (with `{variable}` placeholders), `ejemplos`, `herramientas` (optional) and `validar`. The templates and the shared context are in Spanish, because they are part of the prompts being measured.

`validar` rules:

- `"json"`: the output must parse as JSON.
- `{"etiquetas": [...]}`: the output must be exactly one of the labels.
- `{"resumen": {"vinetas": 3, "max_palabras": 25, "respuesta_exacta": "INSUFICIENTE"}}`: three lines starting with `- `, at most 25 words each, or the exact fallback answer.

## How to run it

```bash
cd semana-05

# Show the request without calling the API
python3 run_prompts.py clasificacion_intencion --var "mensaje=¿Dónde va mi pedido 88421?" --dry-run

# Run it (needs ANTHROPIC_API_KEY in the environment)
set -a; . ../.env; set +a
python3 run_prompts.py extraccion_json --var "correo=Requerimos 60 piezas del SKU LT-9 antes del 3 de diciembre de 2026. Carlos Peña, Refaccionaria Sur."
```

For long variables, use `--archivo variable=path.txt` instead of `--var`.

## Decisions

- **Default model:** `claude-haiku-5-5`. No `temperature` is sent, because this model accepts only the value 1.
- **Prompt caching:** the `system` block carries `cache_control`. The shared context (about 9,900 characters, roughly 2,800 tokens) goes first, so that the fixed part is a cacheable prefix. The log records `tokens_cache_escritura` and `tokens_cache_lectura` (cache write and cache read tokens) to measure the effect.
- **No dependencies:** the runner uses `urllib` so as not to depend on SDKs. That way an SDK change does not alter the library's results.
- **Versioning:** a template changes version when its expected behavior changes. The log keeps the version used in each run, so before and after can be compared.

## Provider comparison (one sample per cell)

The four templates were run with Anthropic (`claude-haiku-5-5`), OpenAI (`gpt-5.6-luna` and `gpt-5.6-terra`) and Gemini (`gemini-3.8-flash`).

| Template | Anthropic | OpenAI (luna) | Gemini (3.8 flash) |
|---|---|---|---|
| `resumen_negocio` | Valid, 4.11 s, input 138 + cache write 3,852, output 303 | Valid, 3.41 s, input 2,307, output 175 | Valid, 7.00 s, input 2,334, output 58 |
| `clasificacion_intencion` | `cotizacion`, valid, 1.09 s, input 139 + cache write 3,811, output 7 | `cotizacion`, valid, 2.43 s, input 2,284, output 5 | `cotizacion`, valid, 1.90 s, input 2,307, output 2 |
| `extraccion_json` | Valid JSON, correct data, 1.06 s, input 255, output 57 | Valid JSON, correct data, 1.76 s, input 2,391, output 32 | Valid JSON, correct data, 4.46 s, input 2,438, output 42 |
| `consulta_inventario` | `buscar_sku` with `AX-204`, 0.95 s, input 97, output 54 | `buscar_sku` with `AX-204`, 2.07 s, input 2,346, output 20 | `buscar_sku` with `AX-204`, 2.87 s, input 2,305, output 20 |

Results of `gpt-5.6-terra` (the same input as luna, one sample per template):

| Template | OpenAI (terra) |
|---|---|
| `clasificacion_intencion` | `cotizacion`, valid, 2.25 s, input 2,284, output 5 |
| `resumen_negocio` | Valid, 1.75 s, input 2,307, output 54 |
| `extraccion_json` | Valid JSON, correct data, 1.03 s, input 2,391, output 32 |
| `consulta_inventario` | `buscar_sku` with `AX-204`, 1.56 s, input 2,346, output 20 |

Notes on reading the tables:

- With OpenAI, `consulta_inventario` needs `reasoning_effort: "none"`. Without it, `gpt-5.6-luna` rejects the tool with HTTP 400 on `chat/completions`. The runner already includes it.
- The input tokens are not directly comparable: OpenAI and Gemini count the shared context (about 2,300 tokens) as input, while Anthropic reports it separately as cache write or cache read. Comparing cost requires adding input plus cache for each provider.
- Anthropic's cache was written for every template. A cache read happened only in the second run of `resumen_negocio`, within 5 minutes.
- Gemini reports no cache tokens in these runs.
- The OpenAI prices (luna: $1.00 / $6.00 per million; terra: $2.50 / $15.00) come from a third-party source and are not verified against official documentation.
- One sample per cell does not support conclusions about quality or cost. It serves to confirm that each provider works with the library.

## Status

- Library: 4 templates, validated in `--dry-run` mode and in real runs, including the validation of `resumen_negocio` (correct request body, examples in alternating user/assistant order, tool defined).
- Real executions against the API (claude-haiku-5-5, 4 runs, all with the correct `stop_reason`):
  - `clasificacion_intencion`: `cotizacion` for "¿me dan precio para 500 cajas al mes?" ("can you give me a price for 500 boxes a month?"). Label validation: correct.
  - `extraccion_json`: valid JSON with the correct customer, SKU, quantity and date. JSON validation: correct.
  - `consulta_inventario`: it called `buscar_sku` with `{"sku": "AX-204"}`, as expected.
  - `resumen_negocio`: three bullets in Spanish, with no introduction. No automatic validation at that point.
- Prompt caching verified: two consecutive runs of `resumen_negocio`. The first wrote 3,852 tokens to the cache (`tokens_cache_escritura`) and the second read them (`tokens_cache_lectura`). In the first version, without the shared context, the cache stayed at 0. The latency difference between the two runs (1.38 s and 1.11 s) is a single sample and is no evidence of an improvement.
- Validation of `resumen_negocio`: implemented and tested with six synthetic cases (three bullets, two bullets, no dash, too many words, the exact fallback answer, and the fallback with extra text). All pass.
- Observed latencies: 0.8 to 2.0 s per call. These are four runs, so they are not a benchmark.
- Multi-model comparison: complete. Four templates with Anthropic, OpenAI (luna and terra) and Gemini (3.8 flash).
- API key: read from `semana-05/.env` (ignored by Git) or from the environment. It is never versioned.
- Automatic eval of the templates: built in week 6, on top of `prompt-evaluator`.
