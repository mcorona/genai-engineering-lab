import math
import os
import mlx.core as mx
from mlx_lm import load

RUTA = os.path.expanduser("~/.lmstudio/models/lmstudio-community/Qwen3.8-27B-MLX-4bit")
model, tok = load(RUTA)

mensajes = [{"role": "user", "content": "Di hola"}]
prompt = tok.apply_chat_template(
    mensajes, add_generation_prompt=True, enable_thinking=False, tokenize=False
)
ids = mx.array(tok.encode(prompt))[None]

logits = model(ids)[0, -1]
logp = logits - mx.logsumexp(logits)
for i in mx.argsort(-logp)[:10].tolist():
    print(f"{tok.decode([i])!r:>12}  p = {math.exp(logp[i].item()):.4f}")
