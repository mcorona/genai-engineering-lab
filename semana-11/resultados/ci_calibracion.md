# Activity 8: CI threshold calibration

Workflow `.github/workflows/eval-semana-11.yml`, script `semana-11/ci/eval_ci.py`. It has two separate jobs, one per suite:

- **`semana11-recuperacion`:**
  - Rebuilds `semana10.chunks` in the pgvector service.
  - Takes the top 20 with the tenant and role filter, and reranks them with Haiku 5.5.
  - Computes exact metrics on the 65 answerable questions per language.
- **`semana11-generacion`:**
  - Uses the fixed contexts of activity 4, the Haiku 5.5 `medium` generator with the `solo_documentos` prompt, and the Haiku 5.5 `low` judge.
  - Runs all 150 questions.

The workflow runs on every pull request. A first job checks whether the PR touches `semana-11/**` or the workflow itself; if not, both suites are skipped. That way they can be required checks without blocking PRs from other weeks.

**Generation subset: no.**
- The activity 7 table estimated ≈ $0.22 per run for the generation suite, and the calibration run cost $0.158.
- Both suites together cost ≈ $0.22 per PR.

**No RAGAS in retrieval:**
- Context precision is AP@5 with a judge (Pearson 0.84, activity 2).
- It would make the retrieval suite about 4 times more expensive (activity 7).
- Reranking is already detected by recall@3 and AP@5.

**Rule (week 10, fixed before running):** threshold = the multiple of 0.05 just below (first-run value − max(0.03, 1/n)).
- n is the number of questions per language: 65 answerable, 10 unanswerable.
- CI values differ from local ones because CI uses `text-embedding-3-small` (OpenAI) instead of bge-m3. That is why calibration uses the CI run.

## Runs (PR #57, 2026-10-28)

| Run | Commit | Thresholds | Cost |
|---|---|---|---|
| 1, calibration | `83a9583` (`--calibrar`) | printed, not applied | $0.222 |
| 2, with thresholds | `114c6ca` | applied: **all checks passed** in both jobs | $0.225 |

## Retrieval (n = 65 per language)

| Metric | ES run 1 | ES run 2 | ES threshold | EN run 1 | EN run 2 | EN threshold |
|---|---|---|---|---|---|---|
| recall@3 | 1.000 | 0.992 | 0.95 | 0.985 | 0.992 | 0.95 |
| recall@5 | 1.000 | 1.000 | 0.95 | 1.000 | 1.000 | 0.95 |
| MRR | 0.931 | 0.969 | 0.90 | 0.958 | 0.962 | 0.90 |
| nDCG@10 | 0.951 | 0.979 | 0.90 | 0.971 | 0.973 | 0.90 |
| AP@5 | 0.933 | 0.971 | 0.90 | 0.955 | 0.963 | 0.90 |

- Failed reranking: 0/130 in both runs.
- Cost: $0.064 per run.
- Step duration: 71 to 76 s.

## Generation (n = 65 answerable and 10 unanswerable per language)

| Metric | ES run 1 | ES run 2 | ES threshold | EN run 1 | EN run 2 | EN threshold |
|---|---|---|---|---|---|---|
| faithfulness (RAGAS) | 0.833 | 0.864 | 0.80 | 0.829 | 0.830 | 0.75 |
| answer relevancy (RAGAS) | 0.850 | 0.853 | 0.80 | 0.819 | 0.836 | 0.75 |
| correctness (custom judge) | 1.000 | 1.000 | 0.95 | 1.000 | 1.000 | 0.95 |
| citation precision | 0.728 | 0.684 | 0.65 | 0.759 | 0.782 | 0.70 |
| no false abstention | 1.000 | 1.000 | 0.95 | 1.000 | 1.000 | 0.95 |
| correct abstention (n = 10) | 1.000 | 1.000 | 0.90 | 1.000 | 1.000 | 0.90 |

- Missing judge scores: 1 of 470 in each run (Instructor retries exhausted on faithfulness), within the 1% tolerance.
- Cost: $0.158 and $0.162 (generation $0.028; evaluation $0.13).
- Step duration: 154 and 193 s.

## Margin against noise

| Metric | Tightest margin in run 2 | Change between the two runs |
|---|---|---|
| citation precision ES | **0.034** above 0.65 | −0.044 |
| faithfulness EN | 0.080 above 0.75 | +0.001 |
| MRR ES | 0.069 above 0.90 | +0.038 |

- Between two runs of the same code, citation precision ES moved by 0.044. That is more than the 0.03 minimum margin of the rule, and it is the check most likely to fail without a real regression.
- **Rule:** if a single metric fails and no file of its component changed, run the job once more before treating it as a regression.
