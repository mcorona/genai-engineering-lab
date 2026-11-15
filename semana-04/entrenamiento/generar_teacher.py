"""Generates the teacher's answers (Qwen3.8-27B with the rules in the prompt) for the training pairs.

For each training pair, the teacher is asked for SQL, which is executed and compared with the reference.
Output: data/teacher.jsonl, one line per question with ejecuta, coincide and error.

Uses only semana-03/data/lora/train.jsonl. It never touches pares_eval.jsonl: the evaluation stays clean.

Usage (LM Studio with the 27B model loaded; LB_READER_DSN in the environment):
    uv run python semana-04/entrenamiento/generar_teacher.py
    --limite 3   for a quick test
"""
import argparse
import json
import os
import sys
from pathlib import Path

import psycopg
from openai import OpenAI

RAIZ = Path(__file__).resolve().parent
SEM3 = RAIZ.parent.parent / "semana-03"
sys.path.insert(0, str(SEM3))
from evaluar_sql import ejecutar, extraer_sql  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:1234/v1")
    ap.add_argument("--modelo", default="qwen3.8-27b-mlx@4bit")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--reintentar", action="store_true",
                    help="only the questions without SQL in teacher.jsonl; output in teacher_reintento.jsonl")
    args = ap.parse_args()

    reglas = (SEM3 / "reglas_legado.md").read_text(encoding="utf-8")
    pares = [json.loads(l) for l in open(SEM3 / "data" / "lora" / "train.jsonl", encoding="utf-8")]
    if args.reintentar:
        previos = [json.loads(l) for l in open(RAIZ / "data" / "teacher.jsonl", encoding="utf-8")]
        pendientes = {f["pregunta"] for f in previos if not f["sql_maestro"]}
        pares = [p for p in pares if p["messages"][1]["content"] in pendientes]
    if args.limite:
        pares = pares[: args.limite]
    cliente = OpenAI(base_url=args.base_url, api_key="lm-studio", timeout=900)

    salida = RAIZ / "data" / ("teacher_reintento.jsonl" if args.reintentar else "teacher.jsonl")
    aciertos = 0
    with psycopg.connect(os.environ["LB_READER_DSN"]) as conn, open(salida, "w", encoding="utf-8") as fh:
        for i, par in enumerate(pares, 1):
            sistema, pregunta, referencia = (m["content"] for m in par["messages"])
            r = cliente.chat.completions.create(
                model=args.modelo, temperature=0, max_tokens=args.max_tokens,
                messages=[{"role": "system", "content": sistema + "\n\n" + reglas},
                          {"role": "user", "content": pregunta}],
            )
            sql = extraer_sql(r.choices[0].message.content)
            terminacion = r.choices[0].finish_reason
            res_ref, _ = ejecutar(conn, referencia)
            if sql:
                res_mod, error = ejecutar(conn, sql)
            else:
                res_mod, error = None, f"sin SQL (finish_reason={terminacion})"
            ejecuta = res_mod is not None and len(res_mod) > 0
            coincide = ejecuta and res_mod == res_ref
            aciertos += int(coincide)
            fila = dict(pregunta=pregunta, sistema=sistema, referencia=referencia,
                        sql_maestro=sql, ejecuta=ejecuta, coincide=coincide,
                        error=error, finish=terminacion)
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"[{i}/{len(pares)}] executes={ejecuta} matches={coincide} {pregunta[:60]}", flush=True)
    print(f"teacher right on {aciertos}/{len(pares)} training pairs")


if __name__ == "__main__":
    main()
