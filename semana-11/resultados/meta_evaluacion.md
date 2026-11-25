# Activity 3: validating the generation metrics (meta-evaluation)

Script: `experimentos/meta_evaluacion.py` (run on 2026-10-27). Output: `meta_evaluacion_salida.txt`; detail per answer: `meta_evaluacion_detalle.csv`; first run kept as evidence: `meta_evaluacion_salida_corrida1.txt`, `meta_evaluacion_cache_corrida1.json`.

## Design (criteria fixed before running)

- **Sample:** 20 questions per language, the same ids in ES and EN (15 base and 5 non-text, seed 11), among answerable questions whose reference has a figure that does not come from the question.
- **Context:** the top 5 of the adopted pipeline from activity 2; the gold passage is in it for every question.
- **Five answers per question, built by fixed rules, not by a model:**

| Variant | Construction | Expected |
|---|---|---|
| control | Reference answer from activity 1 | High faithfulness and relevance |
| changed figure | First figure of the answer (never one from the question, never a year) × 1.5, or another factor if the new value already appears in the context or would give a percentage above 100 | Faithfulness drops |
| invented claim | Reference + a plausible sentence not in the context ("only for international orders, signed by the CEO") | Faithfulness drops |
| off-topic | Reference of another sampled question about a different document | Answer relevance drops |
| evasive | "I don't have enough information to answer precisely." | Answer relevance drops |

- **Metrics:** RAGAS 0.4.3 faithfulness and answer relevancy (bge-m3 embeddings), and the custom correctness judge from weeks 8 and 10. Judges: Haiku 5.5 `low` and Sonnet 5.5 `low`.
- **A metric detects a variant when** the paired difference against the control has a 95% bootstrap interval below 0 **and** the variant scores below the control in at least 80% of the 40 pairs (ties count half). The control needs mean faithfulness ≥ 0.9.
- **Decision rule:** the cheapest judge that meets the four expected detections and the control.

## Results (40 pairs per cell)

| Metric | Variant | Haiku: difference, below control | Sonnet: difference, below control |
|---|---|---|---|
| faithfulness | changed figure (expected) | −0.837, 96% ✅ | −0.839, 97% ✅ |
| faithfulness | invented claim (expected) | −0.587, 99% ✅ | −0.605, 100% ✅ |
| faithfulness | off-topic | −0.925, 96% | −0.950, 97% |
| faithfulness | evasive | −0.975, 99% | −1.000, 100% |
| answer relevancy | changed figure | −0.001, 55% (not detected) | +0.001, 53% (not detected) |
| answer relevancy | invented claim | −0.058, 80% | −0.036, 82% |
| answer relevancy | off-topic (expected) | −0.521, 100% ✅ | −0.530, 100% ✅ |
| answer relevancy | evasive (expected) | −0.920, 100% ✅ | −0.933, 100% ✅ |
| custom correctness judge | changed figure | −1.000, 100% | −1.000, 100% |
| custom correctness judge | invented claim | −0.475, 74% (not detected) | −0.750, 88% |
| custom correctness judge | off-topic, evasive | −1.000, 100% | −1.000, 100% |

| Control | Haiku | Sonnet |
|---|---|---|
| faithfulness | 0.975 | 1.000 |
| answer relevancy | 0.92 | 0.93 |
| custom judge (correct) | 1.00 | 1.00 |

**Both judges meet the four expected detections and the control.**

## Reading

- **Faithfulness and answer relevancy measure different things, and each catches its own failures.** Faithfulness detects changed figures and invented claims. Relevancy does not notice a changed figure (difference ≈ 0) and barely moves with an invented claim. Relevancy detects off-topic and evasive answers.
- **Faithfulness also drops for off-topic and evasive answers.** Off-topic answers make claims the context does not support. An evasive answer has no claims, so it scores 0. This is the same caveat as the setup check: a **correct abstention also scores 0**, so unanswerable questions need their own metric (activity 4).
- **The custom correctness judge does not replace faithfulness.** It is told that an answer "may add details", so with Haiku it still accepts 53% of the answers with an invented claim, and with Sonnet 25%. It does catch every changed figure, because the essential data contradicts the reference.
- **Misses shared by both judges:**
  - When an answer has two claims and only one figure changes, faithfulness is 0.5 (`rec-47`, `rec-05`, `int-imagen-11`). That still counts as below the control.
  - `rec-49`: the inventory-adjustment threshold changed from $10,000 to $15,000, and both judges gave 1.0.
- **Haiku false alarm:** `int-ocr-06` EN, a correct answer (96.4%), got faithfulness 0.0 from Haiku and 1.0 from Sonnet. It is Haiku's only control below 1 out of 40.

## Decision

**Judge for the rest of week 11: Haiku 5.5 `low` with faithfulness and answer relevancy from RAGAS**, by the rule fixed before running: both judges meet every criterion, and Haiku costs about 14 times less per evaluated answer (≈ $0.0008 vs ≈ $0.011 for the three metrics). Sonnet is slightly cleaner (control 1.000 vs 0.975; no false alarm), which is recorded as a known Haiku limit.

The custom correctness judge stays as a third metric: it catches wrong figures and evasions, but not invented additions. Unanswerable questions are scored with an abstention metric, not with RAGAS.

## Runs and corrections

| Run | What happened | Cost |
|---|---|---|
| 1 | Haiku: all metrics valid. Sonnet: every RAGAS call failed with HTTP 400 (`tool_choice … not supported for this model`), and Sonnet still showed figures identical to Haiku's: the RAGAS disk-cache key does not include the model, so Sonnet received Haiku's cached answers. The custom judge was valid for both. | $0.328 |
| 2 | The 400 invalid Sonnet RAGAS scores were dropped. Sonnet now uses Instructor's JSON mode, and each judge has its own cache. A network failure on the Mac (Python `connect` errno 12, then timeouts) required lowering concurrency to 2, adding retries and a restart. | $2.136 |
| **Total** | | **$2.464** |

Lesson for later activities: never share the RAGAS disk cache between judges, and check that two judges do not give identical figures.

## Limitations

- 20 questions per language and rule-built perturbations: real model errors (a subtly wrong condition, a partial answer) are less clean than a changed number.
- One run per judge; judges are not deterministic.
- The two judges used different Instructor modes (Haiku TOOLS, Sonnet JSON), which is forced by Sonnet 5.5 rejecting forced tool use.
