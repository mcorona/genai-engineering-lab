# Week 6: evals and regression testing in GitHub Actions

> Spanish names (folders, files, JSON keys, flags, stack names, status values) are explained in the [glossary](../docs/glossary.md). The documentation is in English. Spanish data and recorded results stay as they are: the README in each data or results folder describes them in English.

Goal: every prompt or model change is measured before it is merged. The evaluator runs the gold-set cases, applies deterministic checks and an LLM judge for the faithfulness of the summaries, and compares the results against a baseline.

## Structure

| File | Contents |
|---|---|
| `evaluar.py` | The evaluator: it generates the output with the `semana-05` templates, applies the checks and compares with the baseline |
| `golden/casos.jsonl` | 16 gold-set cases (6 classification, 4 extraction, 3 tool use, 3 summary). A draft by the author, pending review |
| `rubricas/fidelidad_resumen.txt` | The judge's rubric: a 1-to-5 scale and JSON output |
| `baseline/resultados_base.json` | The baseline to compare against (generated with `--actualizar-base`) |
| `resultados/` | The report of each run (`eval_<date>.json`) |
| `../.github/workflows/evals-semana-06.yml` | The workflow that runs the evals on every pull request that touches the prompts, the runner or the units that depend on them |

## Checks

- `etiqueta`: the output is exactly the expected label.
- `json_campos`: the output is valid JSON and the listed fields match (`null` counts as a match).
- `herramienta`: the model called `buscar_sku` with the expected input, or called no tool when the case requires that.
- `resumen_estructura`: three bullets of at most 25 words, or `INSUFICIENTE`.
- `juez: true`: on top of the structural check, the judge scores the summary's faithfulness to the document. The case passes with a faithfulness score of 4 or 5.

## Regression

The evaluator fails (exit code 1) if either of these happens with respect to the baseline:

- A case that used to pass now fails.
- The pass rate drops by more than 0.05.

## How to run it

```bash
# from the repository root
python3 semana-06/evaluar.py                      # compares with the baseline if there is one
python3 semana-06/evaluar.py --actualizar-base    # saves this run as the baseline
python3 semana-06/evaluar.py --limite 3           # quick test with 3 cases
```

The key is read from `ANTHROPIC_API_KEY` in the environment or from `semana-05/.env`. In GitHub Actions it comes from the repository secret.

## Decisions

- **The judge is the same model that generates** (`claude-haiku-5-5`). This is a known limitation: a judge from the same family can favor its own outputs. A judge from another family should be tried later.
- **Tools are evaluated by name and input**, not by the text of the response, because in those cases the model writes no text.
- **The baseline is versioned in Git.** If it is updated, it must be in the same commit as the change that justifies it.
- **The gold set is a draft by the author.** Before it is used as a reference, each case must be reviewed with the team.

## Status

- Week 6: closed.
- Evaluator and gold set: created. Deterministic checks and the LLM judge tested.
- Baseline: 16/16 passing, saved in `baseline/resultados_base.json`. The judge gave a faithfulness score of 5 to the two summaries with figures.
- The `ANTHROPIC_API_KEY` secret in GitHub: configured and verified with PR #1. The `regresion` job passed.
- Pending for the next iteration: a judge from another model family, and a review of the gold set with the team.
