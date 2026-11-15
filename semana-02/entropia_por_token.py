"""Next-token entropy along a complete response.

Generates one response by sampling at each temperature (mlx-lm, with a KV cache)
and records, at each position, the probability of the chosen token and the entropy
of that step's distribution (in bits). Positions with high entropy are where the
model could have chosen differently.
"""
import csv
import math
import os

import mlx.core as mx
from mlx_lm import load
from mlx_lm.models.cache import make_prompt_cache

RUTA = os.path.expanduser("~/.lmstudio/models/lmstudio-community/Qwen3.8-27B-MLX-4bit")
PROMPT = "Explica en tres frases qué es el punto de reorden de un SKU y cuándo conviene revisarlo."
TEMPERATURAS = [0.7, 1.0]
SEED = 1
MAX_TOKENS = 200
TOP_MOSTRAR = 8
DIR = os.path.dirname(os.path.abspath(__file__))

model, tok = load(RUTA)
prompt = tok.apply_chat_template(
    [{"role": "user", "content": PROMPT}],
    add_generation_prompt=True, enable_thinking=False, tokenize=False,
)
ids_prompt = tok.encode(prompt)
eos_ids = set(getattr(tok, "eos_token_ids", None) or [tok.eos_token_id])


def distribucion(logits, T):
    z = [x / T for x in logits]
    m = max(z)
    e = [math.exp(x - m) for x in z]
    s = sum(e)
    return [x / s for x in e]


def entropia_bits(p):
    return -sum(x * math.log2(x) for x in p if x > 0)


def generar(T):
    mx.random.seed(SEED)
    cache = make_prompt_cache(model)
    x = mx.array(ids_prompt)[None]
    generados, filas = [], []
    for pos in range(MAX_TOKENS):
        logits = model(x, cache=cache)[0, -1]
        p = distribucion(logits.tolist(), T)
        tok_id = int(mx.random.categorical(logits / T).item())
        contexto = tok.decode(generados[-6:]) if generados else "(inicio)"
        filas.append((pos, contexto, tok_id, p[tok_id], entropia_bits(p)))
        if tok_id in eos_ids:
            break
        generados.append(tok_id)
        x = mx.array([[tok_id]])
    return tok.decode(generados), filas


csv_filas = []
for T in TEMPERATURAS:
    texto, filas = generar(T)
    hs = [f[4] for f in filas]
    print(f"\n=== T = {T} · {len(filas)} tokens · mean entropy {sum(hs)/len(hs):.3f} bits, max {max(hs):.3f} ===")
    print(texto.strip())
    print("\nHighest-entropy positions:")
    for pos, ctx, tid, pe, h in sorted(filas, key=lambda f: -f[4])[:TOP_MOSTRAR]:
        print(f"  pos {pos:3d}  H={h:.2f} bits  chosen {tok.decode([tid])!r:>12} (p={pe:.3f})  after ...{ctx!r}")
    for pos, ctx, tid, pe, h in filas:
        csv_filas.append((T, pos, tok.decode([tid]), round(pe, 6), round(h, 4)))

with open(os.path.join(DIR, "entropia_por_token.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["temperatura", "posicion", "token", "p_elegido", "entropia_bits"])
    w.writerows(csv_filas)
print(f"\nCSV saved to {DIR}/entropia_por_token.csv")
