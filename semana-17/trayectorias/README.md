# Week 17 reference trajectories (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 17 README](../README.md)

The trajectory eval of activity 7 and its frozen references. A trajectory is the sequence of tool calls a run made,
plus the number of model steps it took. A reference says what a good trajectory looks like for one of week 13's 84
gold-set tasks: the required, allowed and forbidden tools, the order constraints and the step range.
`construir_referencias.py` derives the references from the gold set, with no model call, and freezes them with a hash
manifest. The deterministic graders compare a run's trajectory with its reference. They judge the path, not the
answer. The definitions were written before any recorded run was scored (`criterios.py`).

**Why it is in Spanish:** the references name the tools, task IDs and status values of the week 13 MCP server and
gold set, which the lab measures as they are. Translating them would break the match with the recorded runs and the
graders. The keys are explained below.

The results are in [trayectorias.md](../resultados/trayectorias.md) and in the
[week 17 README](../README.md#2-results).

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `referencias.jsonl` | The reference trajectories, one JSON object per gold-set task | `construir_referencias.py` / `correr_eval.py`, `puntuar_semana13.py`, `../tests/test_trayectorias.py` |
| `manifiesto.json` | The manifest that freezes the references: the SHA-256 of `referencias.jsonl`, of the two gold-set files it derives from and of the calibration file, plus the calibration margins per task type | `construir_referencias.py` (`--verificar` rebuilds and compares, and writes nothing) |
| `criterios.py` | What a good trajectory is: the definitions, the pass rules and the calibration set | Read by the other modules |
| `evaluadores.py` | The deterministic graders (pure functions: no I/O, no model) | `correr_eval.py`, `puntuar_semana13.py`, `analisis.py` |
| `adaptadores.py` | The adapter from week 13's trace lines to an abstract trajectory (the span adapter is in `correr_eval.py`) | `correr_eval.py`, `puntuar_semana13.py`, `analisis.py` |
| `construir_referencias.py` | Builds `referencias.jsonl` and `manifiesto.json` from the gold set ($0) | — |
| `puntuar_semana13.py` | Runs the graders on week 13's recorded runs ($0) | Writes `../resultados/trayectorias_semana13.json` |
| `correr_eval.py` | The trajectory eval on the trace, with the scores written to Langfuse ($0 replay, or paid with `--confirmo-gasto`) | Writes `../resultados/trayectorias_real.json` and `../resultados/trayectorias_reproduccion.json` |
| `analisis.py` | The analysis with confidence intervals ($0, reads committed files only) | Writes `../resultados/trayectorias_analisis.json` |
| `__init__.py` | Marks the folder as a Python package | — |

## Keys

| Key | Meaning |
|---|---|
| `id` | Gold-set task ID; the suffix is the language (`-es`, `-en`) |
| `tipo` | Task type: `simple`, `regla` (business rule), `compuesta` (compound), `valores` (value lookup), `ambigua` (ambiguous), `sin_respuesta` (unanswerable) |
| `estado_esperado` | Expected final status: `respondida` (answered) or `requiere_aclaracion` (needs clarification) |
| `requeridas` | Required tools: each must have at least one successful call |
| `permitidas` | Extra tools that are allowed, beyond the required ones |
| `prohibidas` | Forbidden tools (`proponer_orden_compra`, propose a purchase order, on every task) |
| `orden` | Order constraints: pairs `[A, B]` where the first successful call of A must come in an earlier model step than the first call of B |
| `pasos_min`, `pasos_max` | Minimum and maximum reasonable number of model steps |
| `calibracion` | The calibration set the step margin comes from: its file, runs, successful runs (`exitosas`) and margin (`holgura`) per task type |
| `evaluadas` | The recorded runs scored with the references, never used to define them |
| `origen` | The gold-set files the references derive from, with their SHA-256 |
| `sha256` | SHA-256 hashes |
| `tareas` | Number of tasks |
