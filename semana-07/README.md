# Week 7: bilingual NLQ-Inventory evaluation (Spanish and English)

> Spanish names (folders, files, JSON keys, flags, stack names, status values) are explained in the [glossary](../docs/glossary.md). The documentation is in English.

Goal: measure how accurately different LLMs translate natural-language questions into SQL over a legacy-style inventory database, in Spanish and in English, and what each correct answer costs.

## What is measured

- **Execution accuracy:** the predicted SQL and the reference SQL run in a read-only session; their result sets must match as multisets. Column order does not matter, and extra predicted columns are allowed.
- **Cost per correct answer:** input and output tokens times the model price, divided by the number of correct answers. Models without a verified price report no cost.
- **Breakdown by language and by failure type:** `sin_sql` (no valid SELECT), `error_ejecucion` (the database rejects the query), `resultado_distinto` (valid SQL, wrong result).

## Dataset

`datasets/nlq_bilingual.jsonl` has 200 lines: 100 unique questions, each in Spanish (`-es`) and English (`-en`). The questions are generated from templates over the synthetic data in `inventory-copilot` (seed 42). Each question has a reference SQL.

`run_eval.py --validar` runs every reference SQL and keeps only the questions that return rows. The result goes to `datasets/nlq_validado.jsonl`.

This set is held out for measurement only. Prompts are not tuned on it.

## Files

| File | Purpose |
|---|---|
| `build_dataset.py` | Generates the bilingual dataset from templates |
| `build_hard_dataset.py` | Hand-written harder set: 48 questions, bilingual |
| `schema_completo.sql` | Full schema snapshot (`inventory-copilot` files 01 to 03), without roles or grants |
| `datasets/` | Question sets, and their validated versions (`*_validado.jsonl`) |
| `schema.sql` | Schema given to the model (trimmed to the columns the questions use) |
| `run_eval.py` | Runs validation, generates SQL with each model, executes it, compares results and reports. Flags: `--set facil\|dificil\|seguimiento`, `--esquema corto\|completo`, `--citas`, `--sin-historial` |
| `prices.json` | Prices per million tokens, with the source of each figure. `null` means unverified |
| `resultados/` | Per-question detail and per-model summary, one file per run |

## How to run

The database must be running. From `inventory-copilot`, start PostgreSQL with `docker compose up -d`.

From the repo root:

```bash
# Read-only DSN: the copilot_ro role from inventory-copilot/.env (not printed)
export NLQ_DSN="$(grep '^PG_DSN=' ~/inventory-copilot/.env | cut -d= -f2-)"

uv run python semana-07/run_eval.py --validar

uv run python semana-07/run_eval.py --modelos \
  anthropic:claude-haiku-5-5 \
  openai:gpt-5.6-luna \
  openai:gpt-5.6-terra \
  gemini:gemini-3.8-flash
```

API keys are read from the environment or from `semana-05/.env`, as in week 5.

## Design decisions

- **The model sees only the schema and the question.** No examples from the dataset are included, so the questions are not leaked into the prompt.
- **Read-only execution.** Every query runs in a read-only session with a 5-second timeout. Only one SELECT or WITH statement is accepted.
- **The comparator is adapted from `inventory-copilot`.** It is copied, not imported, so this week does not depend on that repository's code.
- **Reference SQL is validated first.** Questions whose reference returns no rows are dropped, so an empty result cannot count as a correct answer.

## Results (final run, 100 questions per language)

Run date: 2026-10-22. Dataset validated: 200 of 200 lines.

| Model | Language | Execution accuracy | Cost (USD, this run) | Cost per correct answer (USD) |
|---|---|---|---|---|
| claude-haiku-5-5 (Anthropic) | EN | 100 / 100 | 0.0034 | 0.000034 |
| claude-haiku-5-5 (Anthropic) | ES | 100 / 100 | 0.0039 | 0.000039 |
| gemini-3.8-flash (Google) | EN | 100 / 100 | 0.0434 | 0.000434 |
| gemini-3.8-flash (Google) | ES | 100 / 100 | 0.0437 | 0.000437 |
| gpt-5.6-luna (OpenAI) | EN | 100 / 100 | 0.0147 | 0.000147 |
| gpt-5.6-luna (OpenAI) | ES | 100 / 100 | 0.0151 | 0.000151 |
| gpt-5.6-terra (OpenAI) | EN | 100 / 100 | 0.1209 | 0.001209 |
| gpt-5.6-terra (OpenAI) | ES | 100 / 100 | 0.1212 | 0.001212 |

Costs are recomputed from the run's token counts with the official prices in `prices.json`, consulted on 2026-10-22. The Gemini price is valid through December 31, 2026; see the note under the harder-set table below. The run summary file still holds the old costs, which used third-party prices for OpenAI and no price for Gemini.

**Reading these results.** Every model answered every question correctly, in both languages. This set does not separate the models, so it cannot rank their accuracy. The only useful difference in this run is cost: Haiku was the cheapest per correct answer, and gpt-5.6-terra was the most expensive.

## Public results: NLQ-Inventory, harder set

This is the table that discriminates between models. The easy set above is saturated, so it cannot rank them. Run: short schema (`schema.sql`), no citations, 43 valid questions per language. Costs are recomputed from the run's token counts with the official prices in `prices.json`. The run summary file still holds the old costs, which used third-party prices for OpenAI and no price for Gemini; they are superseded by this table.

| Model | Language | Execution accuracy | Cost (USD) | Cost per correct answer (USD) |
|---|---|---|---|---|
| claude-haiku-5-5 | EN | 43 / 43 (1.000) | 0.0040 | 0.000093 |
| claude-haiku-5-5 | ES | 41 / 43 (0.953) | 0.0057 | 0.000139 |
| gemini-3.8-flash | EN | 41 / 43 (0.953) | 0.0242 | 0.000590 |
| gemini-3.8-flash | ES | 41 / 43 (0.953) | 0.0243 | 0.000593 |
| gpt-5.6-luna | EN | 42 / 43 (0.977) | 0.0097 | 0.000231 |
| gpt-5.6-luna | ES | 43 / 43 (1.000) | 0.0101 | 0.000235 |
| gpt-5.6-terra | EN | 42 / 43 (0.977) | 0.0759 | 0.001807 |
| gpt-5.6-terra | ES | 41 / 43 (0.953) | 0.0771 | 0.001880 |

Single run per model, so differences of one or two questions are within noise. Prices come from the official pages of each provider, consulted on 2026-10-22: OpenAI's model pages for Luna and Terra, and Google's Gemini API pricing page for Gemini 3.8 Flash. Gemini's price is valid through December 31, 2026; from January 1, 2027 it rises to 1.50 / 7.50 USD per million tokens, so its costs will change.

## Changes made during the evaluation

These changes were made after the first runs, and they apply equally to every model. The earlier runs are kept in `resultados/previos/`.

1. **Output limit raised to 4,096 tokens.** At 1,024 tokens, gemini-3.8-flash was cut off mid-query, because its reasoning tokens count toward the output limit.
2. **NULL counts as 0 in the comparator.** `SUM` without `COALESCE` returns NULL on empty sets; the reference uses `COALESCE(..., 0)`. Both now compare as 0.
3. **Wording of the stock question.** "Stocked" was ambiguous: the reference counts any stock record, while one model counted only positive stock. The question now says "stock record".
4. **Top-N SKU questions return only the SKU.** The questions ask for SKUs, so the reference no longer returns the total as an extra column that the comparator would require.
5. **Ties broken deterministically.** Ranking queries add `p.sku` as a tie-breaker, and one ambiguous supplier-ranking question was replaced with a count.
6. **Retries and error categories.** Network and server errors are retried up to three times. Quota and billing errors (4xx other than 429) are not retried and are recorded as `error_api`.

## Second iteration: harder set, citations, full schema, follow-ups

Every run writes `set`, `esquema`, `citas` and `sin_historial` into its summary, so each file records its own configuration. Each run is a single pass per model.

### Harder set (`--set dificil`)

- 48 hand-written questions in Spanish and English (`build_hard_dataset.py`). Each question states its own tie-break and rounding rule. They cover multi-table joins, correlated subqueries, anti-joins, window functions, date windows and `HAVING` thresholds.
- Validation keeps 86 of 96 lines, which is 43 questions per language. The discarded questions are `hard-013`, `018`, `023`, `030` and `046`. Their reference SQL returns no rows, mostly because of the data (for example, every product has sales). Two more questions with empty results were removed after the runs (see Changes).
- Result with the short schema (`schema.sql`) and no citations, correct out of 43 per language:

| Model | EN | ES |
|---|---|---|
| claude-haiku-5-5 | 43 | 41 |
| gemini-3.8-flash | 41 | 41 |
| gpt-5.6-luna | 42 | 43 |
| gpt-5.6-terra | 42 | 41 |

### Experiment 1: full schema (`--esquema completo`)

The full schema is the snapshot of `inventory-copilot/db/init` files 01 to 03, with roles, grants and passwords removed. It tests the effect of a longer context.

The first run was confounded. The snapshot had dropped the value hints that `schema.sql` carries (country codes, category names, city names), and the models then wrote `'Germany'` and `'China'`. The snapshot now carries the same hints. The confounded run is archived in `resultados/previos/` and is not used for any conclusion. The corrected run is recorded below.

### Experiment 2: citations (`--citas`)

The model lists the tables it read on a final `TABLES:` line. Correct answers stayed the same as without citations: claude-haiku-5-5 42/42, gemini-3.8-flash 42/41, gpt-5.6-luna 42/43, gpt-5.6-terra 42/42 (EN/ES).

- Exact match between cited and reference tables: 0.91 to 0.98.
- Precision: 0.97 to 0.99.
- Exhaustiveness: 0.99 to 1.00.

The reference tables come from a regex over the reference SQL, so the citation scores are a proxy, not a ground truth.

### Experiment 3: follow-up questions (`--set seguimiento`)

Twenty follow-up questions in each language. The previous turn is sent as an example in the conversation. The previous turn uses the reference SQL, so model errors do not carry into the next turn.

The first run, before the rewrites below, scored 154 of 160: claude-haiku-5-5 38/40, gpt-5.6-luna 38/40, gpt-5.6-terra 38/40, gemini-3.8-flash 40/40. The run is archived in `resultados/previos/`.

This score does not show that the previous turn is what makes the answers correct. The control is recorded below.

### Changes made during this iteration

1. **Full-schema snapshot corrected.** The first snapshot dropped the value hints from `schema.sql`. They are restored, and the confounded run is archived.
2. **Two follow-ups reworded to remove ambiguity (`seg-003`, `seg-016`, both languages).** The reference SQL did not change. The wording was changed after the first run had been read, and that run is archived as the before-state.
3. **Control flag added.** `--sin-historial` omits the previous turn.
4. **Follow-up `seg-011` reworded (after the results were read).** The follow-up "And what is its average unit cost?" was read by one model as the average over critical products only. The reference averages all products in the category. The wording now says "all products ... including the non-critical ones". The reference SQL did not change. The runs with the earlier wording are archived in `resultados/previos/`.
5. **Two empty-result questions removed.** The old `hard-039` (category "Seguridad") and `hard-040` (a threshold) returned no rows. Rather than correct them after seeing the results, they were removed. Questions old `hard-041` to `048` were renumbered to `039` to `046`. The validated set was remapped by language and SQL, so the 43 valid questions per language are unchanged and the results above still apply. The earlier runs in `resultados/previos/` use the old numbering.

### Results after the corrected runs

Full schema, corrected snapshot, no citations. Correct out of 43 per language, with the short-schema results from the harder-set table above in the last column:

| Model | EN | ES | Short schema, no citations (EN / ES) |
|---|---|---|---|
| claude-haiku-5-5 | 43 | 42 | 43 / 41 |
| gemini-3.8-flash | 42 | 42 | 41 / 41 |
| gpt-5.6-luna | 41 | 43 | 42 / 43 |
| gpt-5.6-terra | 40 | 41 | 42 / 41 |

Across both languages, the totals move by −2 to +2 questions out of 86. That is within the noise of one run per model. The earlier drop came from the removed hints, not from the schema length. One run cannot show the schemas are equivalent, only that the difference is small.

Follow-up questions, after the `seg-011` fix. Correct out of 20 per language, with the previous turn (`--set seguimiento`) and without it (`--sin-historial`):

| Model | With history (EN / ES) | Without history (EN / ES) |
|---|---|---|
| claude-haiku-5-5 | 20 / 20 | 4 / 4 |
| gemini-3.8-flash | 20 / 20 | 5 / 5 |
| gpt-5.6-luna | 20 / 20 | 3 / 4 |
| gpt-5.6-terra | 20 / 20 | 4 / 4 |

The with-history score is not an independent result. The wording of `seg-003`, `seg-016` and `seg-011` was changed after reading errors from earlier runs, so the set is tuned to these models and is now saturated, like the easy set. The control is the useful measure: without the previous turn, models get 3 to 5 of 20 per language. About 80 percent of the correct follow-up answers depend on the previous turn.

### Pending

Nothing pending for this iteration.

## Third iteration: three-turn chains (`--set cadenas`)

The follow-up set is saturated with history, and its wording was tuned after reading errors. This set replaces it as the discriminating test of memory, and it was written and committed before any run.

- 16 chains in Spanish and English (`build_cadenas_dataset.py`, 32 lines). Each chain has two previous turns, with their reference SQL, and a final question that depends on them.
- The chains include corrections ("Change it", "Remove the ones..."), references to a turn two steps back, ellipsis ("Now the same for Monterrey"), and unit-of-measure carry-over.
- `cad-14` was reworded after the first run (`cad-14-es`, `cad-14-en`): "¿Y cuántas unidades vendieron en agosto?" became "¿Y cuántas unidades vendieron en total en agosto de 2026?", because the first wording invited a per-SKU breakdown. The reference SQL did not change.
- Every final question has a single reference SQL. Ambiguous references were avoided on purpose. Any change after the first run must be documented here and the earlier runs archived.

### Results (run `20261022T061851Z`, superseded: `cad-14` was reworded, see below)

| Model | Language | Execution accuracy | Cost (USD) | Cost per correct answer (USD) |
|---|---|---|---|---|
| claude-haiku-5-5 | EN | 15 / 16 (0.938) | 0.0024 | 0.000157 |
| claude-haiku-5-5 | ES | 16 / 16 (1.000) | 0.0024 | 0.000149 |
| gemini-3.8-flash | EN | 16 / 16 (1.000) | not verified | not verified |
| gemini-3.8-flash | ES | 15 / 16 (0.938) | not verified | not verified |
| gpt-5.6-luna | EN | 15 / 16 (0.938) | 0.0214 | 0.001429 |
| gpt-5.6-luna | ES | 14 / 16 (0.875) | 0.0222 | 0.001588 |
| gpt-5.6-terra | EN | 15 / 16 (0.938) | 0.0472 | 0.003146 |
| gpt-5.6-terra | ES | 15 / 16 (0.938) | 0.0452 | 0.003017 |

Totals out of 32: claude-haiku-5-5 31, gemini-3.8-flash 31, gpt-5.6-terra 30, gpt-5.6-luna 29. One question is 6.25 points, so these differences are small and come from one run per model.

Failures, reviewed:

- **`cad-14` (5 of 7 failures).** The follow-up "And how many units did they sell in August 2026?" refers to a list of products. Five answers from three models (Haiku EN, Luna EN and ES, Terra EN and ES) returned a per-SKU breakdown, and the reference expects one total. The wording is ambiguous, and the same problem appeared in `seg-016`. The reference SQL did not change.
- **`cad-10` (gpt-5.6-luna, ES).** The model returned a ranking as a CTE. The truncated SQL does not show whether it applies `LIMIT 1`, so this is not fully inspected.
- **`cad-14-es` (gemini-3.8-flash).** Empty output with no SQL. This is an output failure, not a reasoning error.

`cad-14` was reworded after this run (see Changes). This table is superseded, and its run is archived in `resultados/previos/`. A rerun is pending.


### Results after the `cad-14` rewrite (run `20261022T062215Z`)

Short schema, no citations, 16 chains per language. Earlier run `20261022T061851Z` is archived in `resultados/previos/`.

| Model | Language | Execution accuracy | Cost (USD) | Cost per correct answer (USD) |
|---|---|---|---|---|
| claude-haiku-5-5 | EN | 15 / 16 (0.938) | 0.0023 | 0.000156 |
| claude-haiku-5-5 | ES | 15 / 16 (0.938) | 0.0019 | 0.000128 |
| gemini-3.8-flash | EN | 16 / 16 (1.000) | not verified | not verified |
| gemini-3.8-flash | ES | 16 / 16 (1.000) | not verified | not verified |
| gpt-5.6-luna | EN | 15 / 16 (0.938) | 0.0207 | 0.001379 |
| gpt-5.6-luna | ES | 16 / 16 (1.000) | 0.0201 | 0.001257 |
| gpt-5.6-terra | EN | 16 / 16 (1.000) | 0.0464 | 0.002902 |
| gpt-5.6-terra | ES | 16 / 16 (1.000) | 0.0441 | 0.002753 |

Totals out of 32: gemini-3.8-flash 32, gpt-5.6-terra 32, gpt-5.6-luna 31, claude-haiku-5-5 30. Single run per model, one question is 6.25 points.

Failures, reviewed:

- **`cad-14-es` (claude-haiku-5-5).** It dropped the product filter set two turns earlier (unit cost above 500 and critical), and summed all sales in August. This is a real context loss.
- **`cad-14-en` (gpt-5.6-luna).** The English rewrite still allows a per-SKU breakdown, because "they" is plural. The rewrite fixed the Spanish wording and not the English one.
- **`cad-10-en` (claude-haiku-5-5).** The question asks which SKU sold the most, in the singular. The model returned the full ranking instead of one SKU. The Spanish version of the same question was correct.

Two of the three failures are wording or ambiguity issues. One, `cad-14-es`, is a real loss of earlier context.

### Second rewrite of `cad-14` (rerun pending)

Both versions of `cad-14` were reworded again so that the follow-up names the filter from the previous turn explicitly. The reference SQL did not change.

- `cad-14-es`: "¿Y cuántas unidades vendieron en total en agosto de 2026?" became "¿Y cuántas unidades de esos productos críticos se vendieron en total en agosto de 2026?".
- `cad-14-en`: "And how many units did they sell in total in August 2026?" became "And how many units of those critical products were sold in total in August 2026?".

The results above (`20261022T062215Z`) are for the previous wording and remain as the record of that run.

### Results after the second rewrite (run `20261022T223719Z`)

Set `cadenas`, 16 chains per language, schema `corto`, without citations.

| Model | EN | ES |
|---|---|---|
| claude-haiku-5-5 | 15/16 | 15/16 |
| gpt-5.6-luna | 16/16 | 15/16 |
| gpt-5.6-terra | 16/16 | 16/16 |
| gemini-3.8-flash | 16/16 | 16/16 |

`cad-14-en` now passes with all four models. Luna, which failed it before the rewrite, passes it now.

Three failures remain, and they are not reworded. They are documented as they are:

- **`cad-10-en` (claude-haiku-5-5) and `cad-10-es` (gpt-5.6-luna).** The question asks "which of those sold the most" (singular), and the reference uses `LIMIT 1`. Both models returned the full ranking ordered by sales, which is a defensible reading of the question but not the reference. This is an ambiguity in cardinality, not a SQL error. The set was not reworded again, to avoid tuning it to the models after each run.
- **`cad-14-es` (claude-haiku-5-5).** No SQL was extracted from the answer. The detail file does not keep the raw response, so the cause (prose, a clarification request, or truncation) is not known. This is an output failure, not a reasoning error. The same kind of failure appeared with Gemini in earlier runs.

The chains set is closed with these results. The three failures stay in the record as known limits.

## Limits

- **The easy set is saturated.** A perfect score for every model means that its questions are too easy to rank models; the harder set addresses this.
- **Template-generated questions.** They are less varied than real user questions.
- **A single run per model.** No confidence intervals are computed, so compare differences only when they are large relative to the number of questions.
- **Prices.** The OpenAI and Gemini prices were verified on the official pricing pages on 2026-10-22 (`prices.json`). In the first two chain-run tables, the Gemini cost is shown as "not verified": those tables were written before its price was recorded.
- **Prompt caching.** The system prompt is short, so prompt caching is not expected to apply.

## Status

- Week 7 closed. The three-turn chain set was committed before it was run, and it is closed with the results above; its three remaining failures stay in the record as known limits.
- Easy set: 100 questions per language, validated, saturated.
- Harder set: 48 questions, 43 valid per language, results recorded.
- Follow-up set: saturated with history; the control shows that the previous turn drives about 80 percent of the correct follow-up answers.
- Context experiments: full schema, citations and the follow-up control, all recorded.
