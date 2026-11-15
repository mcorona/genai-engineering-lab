# KV cache memory estimate for a client proposal.
# Approximate configurations of typical open models (illustrative).
GiB = 1024 ** 3
BYTES = 2  # fp16

modelos = {
    "small model (~8B)": dict(capas=32, cabezas_kv=8, dim_cabeza=128),
    "large model (~70B)": dict(capas=80, cabezas_kv=8, dim_cabeza=128),
}
contextos = [4_096, 32_768, 131_072]   # tokens per conversation or document
usuarios = [1, 10, 100]                # concurrent conversations


def kv_por_token(m):
    return 2 * m["capas"] * m["cabezas_kv"] * m["dim_cabeza"] * BYTES


for nombre, m in modelos.items():
    print(f"\n{nombre}: {kv_por_token(m) / 1024:.0f} KB of cache per token")
    cabecera = " | ".join(f"{u:>3} user(s)" for u in usuarios)
    print(f"{'context':>10} | {cabecera}")
    for ctx in contextos:
        celdas = " | ".join(
            f"{kv_por_token(m) * ctx * u / GiB:>12.1f} GiB" for u in usuarios
        )
        print(f"{ctx:>10,} | {celdas}")