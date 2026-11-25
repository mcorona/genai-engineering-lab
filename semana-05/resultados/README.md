# Week 5 prompt run log (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 5 README](../README.md)

The log of every real call made with the prompt library. `run_prompts.py` appends one line per call (dry runs and
calls made with `--no-guardar` are not logged): which template and version ran, on which provider and model, the
latency, the token counts (including cache writes and reads), the validation result and the model's output. The earliest lines predate the shared context and
the provider field, so those keys are missing there.

**Recorded evidence:** this is the raw log of the runs, kept exactly as recorded (not edited, not translated). The
outputs are the models' Spanish answers. The English summary of the results is in the week README:
[Provider comparison (one sample per cell)](../README.md#provider-comparison-one-sample-per-cell) and
[Status](../README.md#status).

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `ejecuciones.jsonl` | The run log, one JSON object per call | Appended by `run_prompts.py` |

## Keys

| Key | Meaning |
|---|---|
| `fecha` | Date and time of the call, in UTC |
| `plantilla`, `version` | The template that ran and its version |
| `proveedor` | Provider: `anthropic`, `openai` or `gemini` (absent in the earliest lines, which are all Anthropic) |
| `modelo` | Model id |
| `contexto` | The shared context file prepended to the system prompt (absent in the earliest lines) |
| `latencia_s` | Latency of the call, in seconds |
| `tokens_entrada`, `tokens_salida` | Input and output tokens |
| `tokens_cache_escritura`, `tokens_cache_lectura` | Tokens written to and read from the prompt cache |
| `validacion` | Result of the template's validation rule. `null` = no rule applied: the tool-use template has none, and the first version of `resumen_negocio` had none yet |
| `texto` | The model's text output, in Spanish |
| `herramientas` | Tool calls made by the model: `nombre` (tool name) and `entrada` (its input) |
