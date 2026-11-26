# Week 1 data and loss logs (recorded evidence)

[Glossary](../glossary.md) · [Week 1 README](../../semana-01/README.md)

This guide describes the training input of the bigram models and the loss logs of the mini-GPT runs. The bigram
scripts (`bigram.py`, `bigram_grad.py`, `bigram_mlx.py`) read `names.txt`. `train_minigpt_mlx.py` trains the
mini-GPT on Tiny Shakespeare and writes its loss log to `perdidas.csv`. The other `perdidas_*.csv` files are the logs
of the runs with other settings, saved under a name that gives the width (`n`, the embedding size) and, when it
differs, the learning rate (`lr`). Each run took 2000 steps.

**Language of the input:** `names.txt` is not Spanish. It is the list of English first names from Andrej Karpathy's
*makemore* repository, downloaded by `get_data.sh`. It is kept as the input the bigram models were trained on.

**Recorded evidence:** the `perdidas*.csv` files are the raw loss logs of the training runs, kept exactly as recorded
(not edited, not translated). The week README compares the runs in
[Mini-GPT results (step 5)](../../semana-01/README.md#mini-gpt-results-step-5).

## Files

| File | What it is | Written by / Read by |
|---|---|---|
| `names.txt` | The training data of the bigram models: one first name per line | Downloaded by `get_data.sh`; read by `bigram.py`, `bigram_grad.py`, `bigram_mlx.py` |
| `perdidas.csv` | Loss log of the configuration currently in the script: width 64, learning rate 1e-3 | Written by `train_minigpt_mlx.py` |
| `perdidas_n*.csv` | Loss logs of the other runs. `perdidas_n64.csv` is width 64 with learning rate 3e-3 (its last validation loss matches that row of the README table); `perdidas_n128_lr1e-3.csv` and `perdidas_n128_lr3e-3.csv` are width 128 with the learning rate in the name | Written by `train_minigpt_mlx.py` (as `perdidas.csv`, then renamed) |

## Keys

| Key | Meaning |
|---|---|
| `paso` | Training step. A row is logged every 100 steps, with the training loss (`train`, one batch) and the validation loss (`val`, averaged over several batches) |
