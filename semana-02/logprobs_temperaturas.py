"""Distribución del siguiente token según temperature (T), con entropía.

Usa mlx-lm sobre el mismo modelo que LM Studio. Para cada T divide los logits
entre T antes del softmax; con T = 0 toma el token más probable (argmax).
Entropía en bits: 0 = el modelo está seguro; más alta = más dispersión.
"""
import csv
import math
import os

import mlx.core as mx
from mlx_lm import load

RUTA = os.path.expanduser("~/.lmstudio/models/lmstudio-community/Qwen3.8-27B-MLX-4bit")
PROMPT = "Di hola"
TEMPERATURAS = [0.0, 0.7, 1.0]
TOP_P_NUCLEO = 0.9   # cuántos tokens entran al núcleo con este top_p
MOSTRAR = 10
DIR = os.path.dirname(os.path.abspath(__file__))

model, tok = load(RUTA)
mensajes = [{"role": "user", "content": PROMPT}]
prompt = tok.apply_chat_template(
    mensajes, add_generation_prompt=True, enable_thinking=False, tokenize=False
)
ids = mx.array(tok.encode(prompt))[None]
logits = model(ids)[0, -1].tolist()


def distribucion(logits, T):
    if T == 0:
        mejor = max(range(len(logits)), key=lambda i: logits[i])
        return [1.0 if i == mejor else 0.0 for i in range(len(logits))]
    z = [x / T for x in logits]
    m = max(z)
    e = [math.exp(x - m) for x in z]
    s = sum(e)
    return [x / s for x in e]


def entropia_bits(p):
    return -sum(x * math.log2(x) for x in p if x > 0)


def tamano_nucleo(p, umbral):
    acum, n = 0.0, 0
    for i in sorted(range(len(p)), key=lambda i: -p[i]):
        acum += p[i]
        n += 1
        if acum >= umbral:
            break
    return n


filas = []
for T in TEMPERATURAS:
    p = distribucion(logits, T)
    orden = sorted(range(len(p)), key=lambda i: -p[i])
    print(f"\nT = {T}  entropía = {entropia_bits(p):.3f} bits  "
          f"núcleo top_p={TOP_P_NUCLEO}: {tamano_nucleo(p, TOP_P_NUCLEO)} token(s)")
    for i in orden[:MOSTRAR]:
        if p[i] > 0:
            print(f"  {tok.decode([i])!r:>12}  p = {p[i]:.4f}")
    for i in orden[:50]:
        if p[i] > 0:
            filas.append((T, i, tok.decode([i]), round(p[i], 6)))

with open(os.path.join(DIR, "logprobs_distribucion.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["temperatura", "token_id", "token", "probabilidad"])
    w.writerows(filas)
print(f"\nCSV guardado en {DIR}/logprobs_distribucion.csv")
