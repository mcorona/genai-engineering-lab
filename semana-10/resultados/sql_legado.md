# Activity 2: text-to-SQL over a legacy schema

Run of 2026-10-26. Script: `experimentos/sql_legado.py`. Model: **claude-sonnet-5-5, effort `medium`** ($2 / $10 per million tokens, Anthropic's official pricing page consulted on 2026-10-26).
Set: the week 7 hard set (`semana-07/datasets/nlq_hard_validado.jsonl`), 43 questions per language. Execution accuracy with the same comparator as week 7 (`semana-07/run_eval.py`) and the `copilot_ro` read-only role.

## The legacy schema

`legado/legado.sql` creates the `legado` schema with cryptically named views over the inventory-copilot tables. The data and values are the same; only the names change (`products` → `artmst`, `stock.on_hand` → `exidet.exi_qty`, `sales_daily` → `vtadia`, and so on). That way, the week 7 reference SQL, over the original tables, is still the expected result. In the legacy variants, the generated SQL runs with `search_path = legado`, so the model can only use the cryptic views. Data dictionary: `legado/diccionario.json` (6 tables, 26 columns, in Spanish, with example values).

## Variants

- **copilot:** the original schema (`semana-07/schema.sql`), a control with the same model.
- **legado:** the legacy DDL without a dictionary.
- **legado_dic:** the legacy DDL plus the full dictionary.
- **legado_rec:** the DDL and dictionary of only the 3 tables most similar to the question (bge-m3); k = 3 fixed before the run.

## Results

| Variant | Language | Accuracy | Correct | Different result | Not a SELECT | Complete table retrieval | Cost per question (USD) | p50 latency (s) | Output tokens (mean) |
|---|---|---|---|---|---|---|---|---|---|
| copilot | ES | 0.953 | 41/43 | 2 | 0 | - | 0.00298 | 1.7 | 120 |
| copilot | EN | 0.977 | 42/43 | 1 | 0 | - | 0.00298 | 1.8 | 122 |
| legado | ES | 0.977 | 42/43 | 1 | 0 | - | 0.00268 | 1.6 | 164 |
| legado | EN | 0.953 | 41/43 | 2 | 0 | - | 0.00248 | 1.5 | 147 |
| legado_dic | ES | 0.953 | 41/43 | 2 | 0 | - | 0.00433 | 1.8 | 131 |
| legado_dic | EN | 0.977 | 42/43 | 1 | 0 | - | 0.00429 | 1.7 | 129 |
| legado_rec | ES | 0.744 | 32/43 | 9 | 2 | 33/43 | 0.00348 | 1.7 | 176 |
| legado_rec | EN | 0.721 | 31/43 | 10 | 2 | 31/43 | 0.00347 | 1.7 | 180 |

No SQL errors and no truncated outputs. Detail per question: `sql_legado_detalle_claude-sonnet-5-5_medium.csv`.

**Cost:** $1.1475 for 344 calls. In addition: a 24-call pilot, $0.0914 (`sql_legado_detalle_claude-sonnet-5-5_medium_prueba.csv`), and a first attempt that stopped when the API account's balance ran out, with about 43 calls billed (~$0.16, estimated; its results were not saved).

## Comparison with week 7

On the same set and with the original schema, week 7 measured claude-haiku-5-5: ES 41/43 (0.953) and EN 43/43 (1.000), at a cost of $0.0040 to $0.0057 per language (about $0.0001 per question). Sonnet 5.5 in the `copilot` variant scored ES 0.953 and EN 0.977, at $0.0030 per question: **the same accuracy within noise, at 22 to 32 times the cost per question**. That is why Haiku 5.5 was also run on all four variants (next section).

## Haiku 5.5 (an additional run)

The same four variants with **claude-haiku-5-5, effort `medium`** ($0.10 / $0.50 per million, prompts up to 100K tokens). Cost: **$0.0923** for 344 calls. Detail: `sql_legado_detalle_claude-haiku-5-5_medium.csv`.

| Variant | Language | Haiku: accuracy | Sonnet: accuracy | Haiku: cost per question (USD) | Sonnet: cost per question (USD) | Haiku: p50 latency (s) |
|---|---|---|---|---|---|---|
| copilot | ES | 0.977 (42/43) | 0.953 | 0.00021 | 0.00298 | 1.7 |
| copilot | EN | 1.000 (43/43) | 0.977 | 0.00018 | 0.00298 | 1.6 |
| legado | ES | 0.884 (38/43) | 0.977 | 0.00028 | 0.00268 | 2.1 |
| legado | EN | 0.953 (41/43) | 0.953 | 0.00025 | 0.00248 | 2.1 |
| legado_dic | ES | **0.977 (42/43)** | 0.953 | **0.00033** | 0.00433 | 2.0 |
| legado_dic | EN | **1.000 (43/43)** | 0.977 | **0.00032** | 0.00429 | 2.0 |
| legado_rec | ES | 0.767 (33/43) | 0.744 | 0.00029 | 0.00348 | 2.1 |
| legado_rec | EN | 0.721 (31/43) | 0.721 | 0.00029 | 0.00347 | 2.1 |

- **Without the dictionary, Haiku fails on the values, not the names.** It understands the legacy structure, but writes `'ALEMANIA'` or `'China'` where the database stores ISO codes (`'DE'`, `'CN'`), and looks for the city in `alm_dsc` ("CEDIS Norte") instead of `alm_cdd`. That is 7 failures out of 86 in `legado`.
- **The dictionary fixes exactly that:** it brings the format of the values (country codes, cities) and which column holds each piece of data. With it, Haiku matches or beats Sonnet in all four comparable cells.
- **Dictionary retrieval fails the same way as with Sonnet, for the same reason:** 63 of 64 correct with all the tables, 1 of 22 without them. The 14 outputs that are not a SELECT all come from `legado_rec`: refusals when tables are missing.

## Reading

- **The cryptic names did not affect Sonnet:** `legado` scores the same as `copilot` (one question apart, in opposite directions per language). In a 6-table schema, with names such as `artmst` or `exi_qty` and keys that can be inferred, the DDL is enough.
- **The full dictionary did not improve accuracy** and raised the cost per question compared with `legado` (62 % in ES and 73 % in EN), because of the longer prompt.
- **The retrieved dictionary lowered accuracy to 0.72–0.74, and the cause is retrieval, not the SQL:** with every needed table retrieved, 63 of 64 correct; with any table missing, 0 of 22. The table missing most often was `artmst`, the item master (17 of 22), followed by `almmst` (5). Similarity search favors the tables that the question mentions (sales, stock) and leaves out the master table needed for the JOIN.
- **When a table was missing, Sonnet did not invent names:** the 4 outputs that were not a SELECT are explicit refusals ("artmst is not available"). That is the correct behavior with an incomplete schema.

## Decision

**Haiku 5.5 with the legacy DDL and the full dictionary** for the assistant's text-to-SQL: 0.977 ES and 1.000 EN, at $0.00033 per question, about 13 times less than Sonnet with the dictionary ($0.0043), with equal or better accuracy. The dictionary is necessary with Haiku (it supplies the format of the values), although Sonnet did not need it.

Dictionary retrieval is justified only for large schemas, and it would have to extend the retrieved tables with their foreign-key-related tables (for example, always adding the `artmst` master when `exidet` or `vtadia` is retrieved). That variant was not tested.

## Limitations

- One run per variant; 43 questions per language, so one question moves accuracy by 0.023.
- A small schema (6 tables) with cryptic but guessable names. A real legacy schema, with hundreds of tables and patternless abbreviations, would make the dictionary more necessary.
- Two models (Sonnet 5.5 and Haiku 5.5), both with effort `medium`; one run of each.
- k = 3 fixed for retrieval; other values and column-level retrieval were not tested.
