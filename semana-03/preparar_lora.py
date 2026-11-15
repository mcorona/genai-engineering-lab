"""Unit 3: splits the training data into train and valid for mlx-lm.

- data/lora/train.jsonl: the training pairs minus the validation pairs.
- data/lora/valid.jsonl: 10 % of pares_train, to watch the loss during fine-tuning.
- data/pares_eval.jsonl is not used here: it stays untouched as the final test.
"""
import json
import random
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ORIGEN = RAIZ / "data" / "pares_train.jsonl"
DESTINO = RAIZ / "data" / "lora"
DESTINO.mkdir(parents=True, exist_ok=True)

filas = [l for l in ORIGEN.read_text(encoding="utf-8").splitlines() if l.strip()]
random.Random(42).shuffle(filas)
n_valid = round(len(filas) * 0.10)
valid, train = filas[:n_valid], filas[n_valid:]
(DESTINO / "valid.jsonl").write_text("\n".join(valid) + "\n", encoding="utf-8")
(DESTINO / "train.jsonl").write_text("\n".join(train) + "\n", encoding="utf-8")
print(f"train: {len(train)}  valid: {len(valid)}  (eval untouched: data/pares_eval.jsonl)")
