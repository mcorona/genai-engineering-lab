"""Mean entropy per response, repeating the sampling with several seeds.

For each temperature it generates N responses (one per seed) and computes the
mean entropy of the tokens of each one. From those it reports the mean, standard
deviation and 95 % confidence interval per temperature.
Usage:  python entropia_multisemilla.py [N]   (N defaults to 20)
"""
import csv
import math
import os
import statistics
import sys

import mlx.core as mx
from mlx_lm import load
from mlx_lm.models.cache import make_prompt_cache

RUTA = os.path.expanduser("~/.lmstudio/models/lmstudio-community/Qwen3.8-27B-MLX-4bit")
PROMPT = "Explica en tres frases qué es el punto de reorden de un SKU y cuándo conviene revisarlo."
TEMPERATURAS = [0.7, 1.0]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
MAX_TOKENS = 200
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


def generar(T, semilla):
    mx.random.seed(semilla)
    cache = make_prompt_cache(model)
    x = mx.array(ids_prompt)[None]
    generados, hs = [], []
    for _ in range(MAX_TOKENS):
        logits = model(x, cache=cache)[0, -1]
        hs.append(entropia_bits(distribucion(logits.tolist(), T)))
        tok_id = int(mx.random.categorical(logits / T).item())
        if tok_id in eos_ids:
            break
        generados.append(tok_id)
        x = mx.array([[tok_id]])
    return tok.decode(generados), hs


filas = []
for T in TEMPERATURAS:
    textos, medias = [], []
    for semilla in range(1, N + 1):
        texto, hs = generar(T, semilla)
        media, maxima = statistics.mean(hs), max(hs)
        textos.append(texto)
        medias.append(media)
        filas.append((T, semilla, len(hs), round(media, 4), round(maxima, 4), texto.strip()))
        print(f"T={T} seed={semilla:2d}  tokens={len(hs):3d}  mean H={media:.3f}  max H={maxima:.2f}", flush=True)
    desv = statistics.stdev(medias)
    ee = desv / N ** 0.5
    print(f"\n>>> T = {T}: mean H {statistics.mean(medias):.3f} bits "
          f"(sd {desv:.3f}, 95% CI [{statistics.mean(medias)-1.96*ee:.3f}, {statistics.mean(medias)+1.96*ee:.3f}]), "
          f"distinct responses: {len(set(textos))}/{N}\n", flush=True)

with open(os.path.join(DIR, "entropia_multisemilla.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["temperatura", "semilla", "tokens", "entropia_media_bits", "entropia_max_bits", "respuesta"])
    w.writerows(filas)
print(f"CSV saved to {DIR}/entropia_multisemilla.csv")
