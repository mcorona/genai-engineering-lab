# Unit 4: distillation and DPO (extra practice)

Fine-tuning a small model on the answers of a large one (distillation) and on preferences between answers (DPO), using the same legacy schema and the same evaluation as unit 3.

## Design

- **Teacher:** Qwen3.8-27B with the business rules in the prompt. It is the best method measured in unit 3 (a 50.0 % result match).
- **Student:** Qwen2.5-Coder-7B, without rules in the prompt.
- **Training data:** only `semana-03/data/lora/train.jsonl` (157 questions). The evaluation set (`pares_eval.jsonl`, 46 pairs) enters no step.

This tests context distillation: whether the student learns to apply the rules without having them in the prompt.

## Steps

1. `generar_teacher.py`: the teacher answers the 157 training questions. Each answer is executed and compared with the reference. Output: `data/teacher.jsonl`.
2. `construir_datasets.py`: builds two datasets from `teacher.jsonl`:
   - `destilacion/train.jsonl`: question -> the teacher's SQL, only where it was right. The system prompt has no rules.
   - `dpo/train.jsonl`: prompt -> `chosen` (the reference SQL) and `rejected` (the teacher's SQL), only where it was wrong.
3. Training:
   - Distillation: LoRA with mlx-lm on `destilacion/`, as in unit 3.
   - DPO: pending confirmation of the format that the installed version of `mlx-lm` accepts.
4. Evaluation: the distilled student and the DPO student are run with `evaluar_sql.py` on `pares_eval.jsonl`, and compared with the 7B base and the 27B model with rules using `estadistica.py`.

## How to run it

It needs LM Studio with the 27B model loaded and `LB_READER_DSN` in the environment (the same LegacyBridge `.env` used in unit 3).

```bash
# from the repository root
set -a; source ~/legacybridge-v2/.env; set +a
caffeinate -i uv run python semana-04/entrenamiento/generar_teacher.py
uv run python semana-04/entrenamiento/construir_datasets.py
```

The first command takes several hours: 157 questions, each with up to 8192 tokens of 27B reasoning.

## Results

The same 46 evaluation pairs as unit 3 (no rules in the prompt).

| Method | Executes | Result match [95% CI] |
|---|---|---|
| 7B base | 80.4 % | 37.0 % [24.5, 51.4] |
| 7B + LoRA v1 (unit 3) | 84.8 % | 37.0 % [24.5, 51.4] |
| 7B + distillation (checkpoint 150) | 84.8 % | 37.0 % [24.5, 51.4] |
| 27B + rules in the prompt (teacher) | 69.6 % | 50.0 % [36.1, 63.9] |

- Distillation vs. the 7B base: the same 46 cases are right, McNemar p = 1.000. The adapter does change the SQL in 14 of 46 answers, but none of the changes alters a correct result.
- The student did not learn the rules that the teacher does apply. With 95 training examples, the adapter learns the format, as LoRA v1 did.

Issues in the run:

- Numerical divergence: the loss became `nan` at iteration 280 with lr 5e-6, and at iteration 60 with lr 1e-5. Checkpoint 150, before any `nan`, is the one used.
- 9 of the 49 hard questions got no SQL from the teacher, so the student never saw those cases.
- DPO was not trained: the installed version of `mlx-lm` has no DPO mode in its CLI.

Decision: the distillation adapter is not used. The unit 3 rule stands: if the prompt is enough, do not fine-tune.

## Decision on DPO

**DPO is not trained in this unit.** Reason: the installed `mlx_lm.lora` CLI has no DPO mode, and writing a custom training loop is out of scope for the unit.

- What is done: the preference dataset `dpo/train.jsonl` (42 pairs; `chosen` = the reference SQL, `rejected` = the teacher's SQL where it was wrong).
- What is missing to use it: a framework with DPO (for example, Hugging Face TRL) running on a GPU or in a supported environment. It remains future work.
- This decision does not change the unit's conclusion: with 46 evaluation pairs, supervised fine-tuning did not improve the result either, so there is no evidence to prioritize DPO.
