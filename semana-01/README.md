# Week 1: a mini-GPT in MLX, from a bigram model to a transformer block

> Spanish names (folders, files, JSON keys, flags, stack names, status values) are explained in the [glossary](../docs/glossary.md). The documentation is in English. Spanish data and recorded results stay as they are: the [data guide](../docs/data/README.md) and the README in each data or results folder describe them in English.

Project: genai-engineering-lab (formerly AI-projects-llm-internals) · Phase 1 (LLM fundamentals in depth)
Reference: Andrej Karpathy's *Neural Networks: Zero to Hero* series, implemented in MLX.

## Status

- [x] Step 1: MLX installed. The Apple Silicon GPU responds (`Device(gpu, 0)`).
- [x] Step 2: a bigram model in MLX (`bigram_mlx.py`). Loss from 3.3120 to 2.4819.
- [x] Step 3: one attention head with a causal mask (`attention_mlx.py`). The weights of token 0 are `[1, 0, 0, 0]`, and the output matches `mx.fast`.
- [x] Step 4: the full mini-GPT block (`minigpt_mlx.py`). 30,400 parameters; causality test passed.
- [x] Step 5: training on Tiny Shakespeare with a loss log (`train_minigpt_mlx.py`, `perdidas.csv`).

## How to read the bigram loss

The loss is the average negative log-likelihood, `-log p(correct next character)`, averaged over the 228,146 bigrams in the dataset. Lower is better.

- **Step 0 (≈ 3.31):** with random weights, the model spreads the probability almost evenly over the 27 characters. That gives `ln(27) ≈ 3.30`, so the initial value is the expected one.
- **Step 199 (≈ 2.48):** the loss plateaus. This is the limit of a model that only looks at the previous character.
- **Interpretation:** `exp(2.48) ≈ 12`. On average, the model is choosing among about 12 plausible next characters (its perplexity).

## Why the 27×27 table is equivalent to counts

- Each row `i` stands for a current character. Its 27 values are the logits of the next character.
- A `softmax` over each row turns the logits into a probability distribution.
- Bigram counts are also a 27×27 table: `N[i, j]` counts how often `j` follows `i`. Normalizing each row of `N` gives the same information as the learned table.
- Gradient training converges to an approximation of that distribution, because minimizing the loss is equivalent to maximizing the likelihood of the bigrams. That is why the final loss of `bigram_mlx.py` ends up close to that of `bigram_grad.py`.

## Why the regularization term exists

The `0.01 * mean(W²)` term penalizes large weights. Without it, the logits of rare bigrams can grow without bound to fit specific cases, and the model becomes overconfident. With 228 thousand bigrams the practical effect is small. In large models, it keeps the training loss from being misleadingly low.

## Four key concepts

- **BPE tokenization:** text is converted into tokens. BPE starts from characters or bytes and merges the most frequent pairs until it reaches the vocabulary size. A text in Spanish usually takes more tokens than the same text in English. Karpathy's mini-GPT uses characters; BPE is the next step.
- **Context window:** the maximum number of tokens the model processes in one pass. In the code it appears as `block_size`. The cost of attention grows with the square of the sequence length.
- **Attention:** each token computes `softmax(Q·Kᵀ/√d)·V`. Q is the query, K is what each query is matched against, and V carries the information. The causal mask prevents attending to future tokens.
- **KV cache:** stores the K and V tensors already computed so they are not recomputed during generation. It takes memory: per token, `2 × layers × KV_heads × head_dim × bytes`. For a 7B-parameter model in fp16 with 4,096 tokens, it is about 2 GB.

## Review questions

- How would the initial loss change if all the weights were zero instead of random?
- Why does causal attention need a mask while the bigram model does not?
- Which part of the cost of generating a new token grows with the context: the model weights or the KV cache?

## Mini-GPT results (step 5)

Shared configuration: character-level tokenization, `block=64`, `batch=32`, 2000 steps, AdamW. Each run saves its curve in `perdidas_*.csv`.

| Configuration | Final val | Final train | Val-train gap |
|---|---|---|---|
| n=64, lr=3e-3 | 1.87 | 1.75 | 0.12 |
| n=64, lr=1e-3 | 1.74 | 1.57 | 0.17 |
| n=128, lr=1e-3 | 1.72 | 1.54 | 0.18 |

Conclusions:

- The learning rate was the dominant factor. Lowering it from 3e-3 to 1e-3 improved validation by 0.13. With a width of 128, an `lr` of 3e-3 makes the loss oscillate and progress more slowly, because Adam's updates add up over more connections.
- With this training budget, going from a width of 64 to 128 improves validation by only 0.02.
- The val-train gap is almost the same at both widths (0.17 and 0.18). There is no overfitting attributable to capacity in 2000 steps (about 4 passes over the text).
- Observing overfitting would take longer training, for example 10,000 steps, to see whether validation stops improving while the training loss keeps falling.
- The training loss is measured on a single batch and is noisy. For fine comparisons, measure it with `eval_loss` over several batches.
- Samples: all three runs produce text formatted like a play (character names in capitals, line breaks) with recognizable words, and with the spelling errors typical of a character-level model.
- Not comparable with the bigram model: the datasets differ (names vs. Shakespeare, with different vocabularies).
- Bug found: `LR = 2000` instead of `3e-3` made the loss explode (val 9.5e8, then NaN). Lesson: check every configuration variable before running the script.

## Practice: KV cache memory and an architecture decision

Script: `practica_kv_cache.py`. It estimates the cache memory of two reference models (8B and 70B, fp16) for several context lengths and numbers of concurrent users.

Key results:

- Cache per token: 128 KB (8B) and 320 KB (70B).
- Reference case: 60,000-token documents and 50 concurrent queries.
  - 8B model: about 366 GiB of cache.
  - 70B model: about 915 GiB of cache.
- Weights in fp16: about 16 GB (8B) and 140 GB (70B). With many concurrent queries, the cache outweighs the weights.
- With RAG and 4,096 tokens per query, the cache drops to 25 GiB (8B) and 62.5 GiB (70B).

Decision: use RAG as the main lever to reduce memory.

The trade-off to disclose to the client: questions whose answers combine distant parts of the manual can fail, because the retriever may return incomplete chunks.

Mitigation and measurement:

- Measure **hit@k**: the share of questions for which the correct chunk is among the k retrieved.
- Use the client's real questions, including rare ones and ones that span several sections.
- Keep only the most-consulted sections in a fixed context, with prefix caching. That fixed context also takes cache memory, so the savings are partial.

## Next steps (as written at the close of week 1)

1. Week 2: embeddings, sampling and hallucination. With the mini-GPT, try `temp` at 0.5, 0.8 and 1.2 and compare the samples.
2. Repeat the training with `n_layer=4` or `n_embd=128`, and record how much validation improves and how long it takes.
3. Answer the review questions in this note before week 2.
