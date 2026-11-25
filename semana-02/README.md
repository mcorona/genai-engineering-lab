# Week 2: tokens and response variability

> Spanish names (folders, files, JSON keys, flags, stack names, status values) are explained in the [glossary](../docs/glossary.md). The documentation is in English.

A Phase 1 practice: how many tokens the same text costs in Spanish and in English, and how much a model's response varies with `temperature` and `top_p`.

## Files

- `entregable_semana2.ipynb`: the deliverable. The table of tokens per language and the variability chart from the saved runs.
- `texto_es.txt` and `texto_en.txt`: the same content (an inventory reorder policy) in Spanish (231 words) and English (214 words).
- `practica_tokens.py`: counts tokens and computes the cost per text.
- `variabilidad.py`: generates N responses per condition in LM Studio and computes their variability (N defaults to 20).
- `corridas/run1`, `run2`, `run3`: the results of each `variabilidad.py` run.
- `resultados-n5/`: preliminary results with N = 5, before moving to 20.
- `logprobs_mlx.py` and `logprobs_temperaturas.py`: the next-token probability distribution, computed with `mlx-lm`.
- `entropia_por_token.py` and `entropia_multisemilla.py`: the next-token entropy along a response.

---

## Part 1: tokens per language

### Method

| Tokenizer | Kind of count | Notes |
|---|---|---|
| tiktoken `o200k_base` | Exact for that tokenizer | An open proxy, not Claude's tokenizer |
| Qwen2.5 (`Qwen/Qwen2.5-7B-Instruct`) | Exact for its tokenizer | Qwen3 may differ; reported as a proxy for the family |
| Claude `claude-sonnet-5-5` | Official, `count_tokens` API | The 8 message-formatting tokens are subtracted (measured with the letter "a") |

The cost uses the `claude-sonnet-5-5` input rate: **USD 2 per million tokens**, confirmed.

### Results

| Tokenizer | ES | EN | ES/EN | ES overhead | ES cost | EN cost |
|---|---|---|---|---|---|---|
| tiktoken (proxy) | 280 | 246 | 1.14 | 14% | — | — |
| Qwen2.5 | 321 | 246 | 1.30 | 30% | — | — |
| **Claude (official)** | **503** | **371** | **1.36** | **36%** | **$0.001006** | **$0.000742** |

### Conclusions

- With Claude, the same content costs 36% more tokens in Spanish than in English.
- The open proxy (tiktoken) underestimates that overhead: 14% vs. 36%. A budget built with an open tokenizer comes out about 20 points below the real cost in Spanish.
- Qwen is also less efficient in Spanish than tiktoken (30%).
- The cost per text is small, but it scales with volume. For proposals, use Claude's official count and state that the others are estimates.

### Limitations

- The translations differ in length (231 vs. 214 words), so part of the overhead reflects the length of the text and not only the tokenizer. Isolating it would require measuring per character or on equivalent content.
- It is a single sample text. The measurement should be repeated with other kinds of documents (technical, legal, conversational).
- The official count includes 8 fixed formatting tokens, which are subtracted in the table.

---

## Part 2: response variability

### Method

- Model: `qwen3.8-27b-mlx@4bit` in LM Studio (local).
- Prompt (in Spanish): "Explica en tres frases qué es el punto de reorden de un SKU y cuándo conviene revisarlo." ("Explain in three sentences what a SKU's reorder point is and when it should be reviewed.")
- 20 responses are requested per condition. The variability of each response is 1 minus its average Jaccard similarity to the others (over lowercase words); 0 means that all responses are identical.
- A `temperature` sweep with `top_p` = 1.0, and a `top_p` sweep with `temperature` = 1.0.
- **3 runs** were made (60 responses per condition). The confidence interval is an approximate 95% interval (normal) over the 60 values.

### Results

| Condition | Run 1 | Run 2 | Run 3 | Mean | 95% CI |
|---|---|---|---|---|---|
| temperature 0.0 | 0.150 | 0.000 | 0.000 | 0.050 | [0.024, 0.076] |
| temperature 0.7 | 0.665 | 0.603 | 0.600 | 0.623 | [0.608, 0.637] |
| temperature 1.0 | 0.695 | 0.700 | 0.725 | 0.707 | [0.685, 0.729] |
| top_p 0.5 | 0.536 | 0.526 | 0.539 | 0.534 | [0.527, 0.540] |
| top_p 0.9 | 0.657 | 0.647 | 0.677 | 0.661 | [0.643, 0.678] |
| top_p 1.0 | 0.657 | 0.693 | 0.657 | 0.669 | [0.654, 0.684] |

### Conclusions

- **Temperature:** from 0.7 to 1.0 the variability clearly increases; the intervals do not overlap.
- **Top_p:** at 0.5 the variability is clearly lower. Between 0.9 and 1.0 the intervals overlap, so this experiment cannot show that they differ.
- **Temperature 0.0** does not always give zero: run 1 gave 0.150. The cause is not identified; it could be runtime non-determinism in that execution.

### Limitations

- Jaccard measures variation in words, not in meaning. Two responses with the same content and different wording score as different.
- One prompt and one local model. The results do not generalize to other models or prompts without repeating the experiment.
- The Claude models (Sonnet 5.5, Opus 5.5, Fable 5.1) do not accept an arbitrary `temperature`; Haiku 5.5 accepts only `temperature` = 1 and `top_p` = 0.99. That is why the sweep was run with a local Qwen model.
- The 60 values per condition are not independent, because they share responses within each run. The intervals are somewhat optimistic.
- The difference between `top_p` 0.9 and 1.0 is not resolved with 3 runs.

---

## Per-token probabilities

### What each API exposes

- **Anthropic (Messages API):** it does not expose logprobs. The `Create a Message` reference has no probability parameters or fields.
- **LM Studio (`/v1/chat/completions`):** it accepts `logprobs` but returns `null`. There are no per-token probabilities from the API.

That is why the probabilities were computed locally with `mlx-lm` on the same model.

### First-token distribution

Prompt "Di hola" ("Say hello"), with `enable_thinking=False`:

| T | Entropy (bits) | p(`¡`) |
|---|---|---|
| 0.0 | 0.000 | 1.0000 |
| 0.7 | 0.147 | 0.9826 |
| 1.0 | 0.612 | 0.9209 |

The first token barely varies. With `top_p` = 0.9, the nucleus is a single token at all three temperatures.

### Entropy along the response

With 20 seeds per temperature (`entropia_multisemilla.py`), the mean entropy per response is:

| T | Mean entropy (bits) | 95% CI | Distinct responses |
|---|---|---|---|
| 0.7 | 0.518 | [0.502, 0.534] | 20/20 |
| 1.0 | 0.954 | [0.898, 1.010] | 20/20 |

The uncertainty concentrates in the wording (valid synonyms such as *asegurar* and *garantizar*, both "ensure"), not in the meaning. That partly explains why Jaccard measures lexical variation rather than variation in content.

---

## How to run it

```bash
# from the repository root

# Tokens and the deliverable
uv run --with jupyter jupyter lab semana-02/entregable_semana2.ipynb

# Variability (LM Studio running with qwen3.8-27b-mlx@4bit)
uv run python semana-02/variabilidad.py 20

# Entropy per seed
uv run python semana-02/entropia_multisemilla.py 20
```

To count tokens from a script: `uv run python semana-02/practica_tokens.py`. The official Claude count needs `ANTHROPIC_API_KEY` in the environment.
