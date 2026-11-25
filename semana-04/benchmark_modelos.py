"""Latency, throughput and cost benchmark: a local quantized model vs. an API.

Runs the same set of queries against two OpenAI-compatible targets and records,
per query: latency, output tokens, tokens per second and cost.

Usage (local in LM Studio and the API on OpenRouter, for example):

    uv run python semana-04/benchmark_modelos.py \
        --consultas semana-04/consultas.jsonl \
        --local-url http://localhost:1234/v1 --local-modelo qwen3.8-27b-mlx@4bit \
        --api-url https://openrouter.ai/api/v1 --api-modelo <model-id> \
        --api-key-env OPENROUTER_API_KEY \
        --precio-in 0.50 --precio-out 1.50 --nombre semana4

Prices are USD per million tokens for the API; use 0 for the local model (electricity
cost not included; this is stated in the README).

The API key is read from the given environment variable, never from the command line.
"""
import argparse
import csv
import json
import os
import statistics
import time
from pathlib import Path

from openai import OpenAI

RAIZ = Path(__file__).resolve().parent


def percentil(valores, p):
    if not valores:
        return float("nan")
    orden = sorted(valores)
    k = (len(orden) - 1) * p
    f = int(k)
    c = min(f + 1, len(orden) - 1)
    return orden[f] + (orden[c] - orden[f]) * (k - f)


def cargar_consultas(ruta, limite):
    filas = [json.loads(l) for l in open(ruta, encoding="utf-8") if l.strip()]
    return filas[:limite] if limite else filas


def correr_destino(nombre, cliente, modelo, consultas, max_tokens, temperatura, precio_in, precio_out, detalle):
    filas = []
    extra = {} if temperatura is None else {"temperature": temperatura}
    for q in consultas:
        inicio = time.perf_counter()
        try:
            r = cliente.chat.completions.create(
                model=modelo,
                messages=[{"role": "user", "content": q["pregunta"]}],
                max_tokens=max_tokens,
                **extra,
            )
            latencia = time.perf_counter() - inicio
            uso = r.usage
            t_in = uso.prompt_tokens if uso else 0
            t_out = uso.completion_tokens if uso else 0
            costo = (t_in * precio_in + t_out * precio_out) / 1_000_000
            error = ""
        except Exception as e:  # record the failure and move on to the next query
            latencia = time.perf_counter() - inicio
            t_in = t_out = 0
            costo = 0.0
            error = type(e).__name__
        fila = {
            "destino": nombre,
            "id": q.get("id", ""),
            "latencia_s": round(latencia, 4),
            "tokens_entrada": t_in,
            "tokens_salida": t_out,
            "tokens_por_s": round(t_out / latencia, 2) if latencia > 0 and t_out else 0,
            "costo_usd": round(costo, 8),
            "error": error,
        }
        filas.append(fila)
        detalle.append(fila)
        print(f"[{nombre}] {fila['id']:>6} {latencia:6.2f}s {t_out:5d} tok {error}")
    return filas


def resumir(nombre, filas):
    ok = [f for f in filas if not f["error"]]
    lat = [f["latencia_s"] for f in ok]
    tps = [f["tokens_por_s"] for f in ok if f["tokens_por_s"]]
    n = len(filas)
    costo_total = sum(f["costo_usd"] for f in filas)
    return {
        "destino": nombre,
        "consultas": n,
        "errores": n - len(ok),
        "latencia_p50_s": round(percentil(lat, 0.50), 3),
        "latencia_p95_s": round(percentil(lat, 0.95), 3),
        "latencia_media_s": round(statistics.mean(lat), 3) if lat else None,
        "tokens_por_s_mediana": round(statistics.median(tps), 2) if tps else None,
        "costo_total_usd": round(costo_total, 6),
        "costo_por_1k_consultas_usd": round(costo_total / n * 1000, 4) if n else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--consultas", "--queries", type=Path, default=RAIZ / "consultas.jsonl", metavar="QUERIES")
    ap.add_argument("--local-url", default="http://localhost:1234/v1")
    ap.add_argument("--local-modelo", "--local-model", default=None, help="required unless you use --solo api", metavar="LOCAL_MODEL")
    ap.add_argument("--api-url", default="https://openrouter.ai/api/v1")
    ap.add_argument("--api-modelo", "--api-model", default=None, help="required unless you use --solo local", metavar="API_MODEL")
    ap.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    ap.add_argument("--precio-in", "--price-in", type=float, default=0.0, help="USD per million input tokens (API)", metavar="PRICE_IN")
    ap.add_argument("--precio-out", "--price-out", type=float, default=0.0, help="USD per million output tokens (API)", metavar="PRICE_OUT")
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--temp-local", type=float, default=0.0, help="local temperature; 0 for reproducibility")
    ap.add_argument("--temp-api", type=float, default=None,
                    help="API temperature; empty = do not send it (Haiku 5.5 accepts only 1)")
    ap.add_argument("--limite", "--limit", type=int, default=0, help="0 = all", metavar="LIMIT")
    ap.add_argument("--nombre", "--name", default="benchmark", metavar="NAME")
    ap.add_argument("--solo", "--only", choices=["local", "api"], help="run a single target")
    args = ap.parse_args()
    if args.solo != "api" and not args.local_modelo:
        ap.error("--local-modelo is missing")
    if args.solo != "local" and not args.api_modelo:
        ap.error("--api-modelo is missing")

    consultas = cargar_consultas(args.consultas, args.limite)
    print(f"{len(consultas)} queries from {args.consultas}")

    detalle, resumenes = [], []
    if args.solo != "api":
        local = OpenAI(base_url=args.local_url, api_key="lm-studio", timeout=300)
        f = correr_destino("local", local, args.local_modelo, consultas, args.max_tokens, args.temp_local, 0, 0, detalle)
        resumenes.append(resumir("local", f))
    if args.solo != "local":
        clave = os.environ.get(args.api_key_env)
        if not clave:
            raise SystemExit(f"The variable {args.api_key_env} is missing from the environment")
        api = OpenAI(base_url=args.api_url, api_key=clave, timeout=300)
        f = correr_destino("api", api, args.api_modelo, consultas, args.max_tokens, args.temp_api,
                           args.precio_in, args.precio_out, detalle)
        resumenes.append(resumir("api", f))

    salida = RAIZ / "resultados"
    with open(salida / f"{args.nombre}_detalle.csv", "w", newline="", encoding="utf-8") as fh:
        escritor = csv.DictWriter(fh, fieldnames=list(detalle[0].keys()))
        escritor.writeheader()
        escritor.writerows(detalle)
    (salida / f"{args.nombre}_resumen.json").write_text(
        json.dumps({"nombre": args.nombre, "consultas_archivo": str(args.consultas),
                    "max_tokens": args.max_tokens, "temp_local": args.temp_local, "temp_api": args.temp_api, "resumenes": resumenes}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print(json.dumps(resumenes, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
