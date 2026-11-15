"""Unit 2 practice: how many tokens the same text costs in Spanish and in English.

Three counts:
- Qwen: the official Qwen2.5 tokenizer (an exact count with that tokenizer).
- Claude: the API's official count if ANTHROPIC_API_KEY is set; otherwise a tiktoken estimate (declared as such).
- Open tokenizer: tiktoken o200k_base (an exact count with that tokenizer).
"""
import os
from pathlib import Path

import tiktoken
from transformers import AutoTokenizer

ES = Path("texto_es.txt").read_text(encoding="utf-8")
EN = Path("texto_en.txt").read_text(encoding="utf-8")

# Price per million input tokens (USD). Fill it in from the provider's current price table.
PRECIO_POR_MTOK = {"Claude": 2.0, "Qwen": None, "tiktoken": None}  # USD per million input tokens (claude-sonnet-5-5)

resultados = {}  # name -> (tokens_es, tokens_en, method label)

# 1. Open tokenizer (exact)
enc = tiktoken.get_encoding("o200k_base")
resultados["tiktoken"] = (len(enc.encode(ES)), len(enc.encode(EN)), "exacto (o200k_base)")

# 2. Qwen (exact with its own tokenizer)
qtok = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-7B-Instruct")
resultados["Qwen"] = (len(qtok.encode(ES)), len(qtok.encode(EN)), "exacto (Qwen2.5)")

# 3. Claude: official if there is a key; otherwise a declared estimate
if os.getenv("ANTHROPIC_API_KEY"):
    import anthropic

    client = anthropic.Anthropic()

    def contar(texto):
        r = client.messages.count_tokens(
            model="claude-sonnet-5-5",
            messages=[{"role": "user", "content": texto}],
        )
        return r.input_tokens

    # Fixed overhead of the message format: the letter "a" weighs 1 token.
    overhead = contar("a") - 1
    print(f"Claude format overhead: {overhead} tokens (subtracted from each count)")
    resultados["Claude"] = (
        contar(ES) - overhead,
        contar(EN) - overhead,
        f"oficial (API), sin {overhead} tokens de formato",
    )
else:
    resultados["Claude"] = (
        len(enc.encode(ES)),
        len(enc.encode(EN)),
        "ESTIMACIÓN: proxy con o200k_base, no oficial",
    )

print(f"{'tokenizer':<12} | {'ES':>6} | {'EN':>6} | {'ES/EN':>6} | {'ES extra':>8} | method")
for nombre, (es, en, metodo) in resultados.items():
    print(f"{nombre:<12} | {es:>6} | {en:>6} | {es / en:>6.2f} | {(es - en) / en:>7.0%} | {metodo}")

print("\nCost per text (only if PRECIO_POR_MTOK is filled in):")
for nombre, (es, en, _) in resultados.items():
    precio = PRECIO_POR_MTOK.get(nombre)
    if precio:
        print(f"{nombre:<12} ES: ${es / 1e6 * precio:.6f}  EN: ${en / 1e6 * precio:.6f}")
