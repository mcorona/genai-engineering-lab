"""Week 3: evaluates a question -> SQL model against pares_eval.jsonl.

For each pair, the model generates SQL. The model's SQL and the reference SQL are executed with
lb_reader (read-only, 5 s timeout) and the results are compared:
- ejecuta: the model's SQL runs and returns usable rows.
- coincide_resultado: the same rows as the reference (order ignored).
- coincide_sql: the same text as the reference, normalized (a weak measure).

Usage (from the repository root, with LB_READER_DSN in the environment):
    uv run python semana-03/evaluar_sql.py --nombre base
    uv run python semana-03/evaluar_sql.py --nombre lora --base-url http://localhost:8080/v1 --modelo <name>
    --limite 3   for a quick test with 3 pairs
"""
import argparse
import json
import os
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import psycopg
from openai import OpenAI

RAIZ = Path(__file__).resolve().parent
DSN = os.environ["LB_READER_DSN"]

import sys
sys.path.insert(0, str(RAIZ))
from generar_pares import PLANTILLAS  # only the template definitions; it does not touch the database
from rag_reglas import reglas_para

_PATRONES = []
for _p in PLANTILLAS:
    for _pat in _p["preguntas"]:
        _rx = "^" + re.sub(r"\\\{\w+\\\}", ".+?", re.escape(_pat)) + "$"
        _PATRONES.append((_p["id"], re.compile(_rx)))


def plantilla_de(pregunta):
    for nombre, rx in _PATRONES:
        if rx.match(pregunta):
            return nombre
    return "desconocida"


def normalizar_valor(v):
    if v is None:
        return None
    if isinstance(v, (Decimal, float, int)) and not isinstance(v, bool):
        return round(float(v), 2)
    s = str(v).strip()
    if re.fullmatch(r"-?\d+,\d{2}", s):          # coma decimal: 12,50
        s = s.replace(",", ".")
    limpio = re.sub(r"[$,]", "", s)                 # $1,234.50 -> 1234.50
    es_codigo = len(limpio) > 1 and limpio.startswith("0") and "." not in limpio
    if re.fullmatch(r"-?\d+(\.\d+)?", limpio) and not es_codigo:
        return round(float(limpio), 2)
    return s


def ejecutar(conn, sql):
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = '5s'")
            cur.execute(sql)
            filas = cur.fetchall()
        conn.rollback()
    except psycopg.Error as e:
        conn.rollback()
        return None, type(e).__name__
    return sorted((tuple(normalizar_valor(c) for c in f) for f in filas), key=repr), None


def extraer_sql(texto):
    texto = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S).strip()
    bloque = re.search(r"```(?:sql)?\s*(.*?)```", texto, flags=re.S | re.I)
    sql = bloque.group(1) if bloque else texto
    return sql.strip().rstrip(";").strip()


def normalizar_sql(sql):
    return re.sub(r"\s+", " ", sql).strip().lower()


def reevaluar(nombre):
    """Re-executes the saved SQL (the model's and the reference) and recomputes the metrics."""
    filas = [json.loads(l) for l in open(RAIZ / "resultados" / f"{nombre}_detalle.jsonl", encoding="utf-8")]
    with psycopg.connect(DSN) as conn:
        for f in filas:
            res_ref, _ = ejecutar(conn, f["sql_referencia"])
            res_mod, error = ejecutar(conn, f["sql_modelo"]) if f["sql_modelo"] else (None, "sin SQL")
            f["ejecuta"] = res_mod is not None and len(res_mod) > 0
            f["coincide_resultado"] = f["ejecuta"] and res_mod == res_ref
            f["error"] = error
    n = len(filas)
    resumen = dict(nombre=nombre + "_reevaluado", pares=n,
                   ejecuta=round(sum(f["ejecuta"] for f in filas) / n, 3),
                   coincide_resultado=round(sum(f["coincide_resultado"] for f in filas) / n, 3))
    (RAIZ / "resultados" / f"{nombre}_reevaluado_resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nombre", "--name", default="", help="result label: base, lora, ...", metavar="NAME")
    ap.add_argument("--base-url", default="http://localhost:1234/v1")
    ap.add_argument("--modelo", "--model", default="qwen3.8-27b-mlx@4bit", metavar="MODEL")
    ap.add_argument("--limite", "--limit", type=int, default=0, metavar="LIMIT")
    ap.add_argument("--reglas", "--rules", action="store_true", help="add all the rules to the system prompt")
    ap.add_argument("--rag", action="store_true", help="add only the rules relevant to each question")
    ap.add_argument("--reevaluar", "--rescore", default="", help="recompute the metrics of a saved detail file, without a model", metavar="DETAIL_FILE")
    args = ap.parse_args()

    if args.reevaluar:
        reevaluar(args.reevaluar)
        return
    if not args.nombre:
        ap.error("--nombre is missing (or use --reevaluar NOMBRE)")

    pares = [json.loads(l) for l in open(RAIZ / "data" / "pares_eval.jsonl", encoding="utf-8")]
    if args.limite:
        pares = pares[: args.limite]
    cliente = OpenAI(base_url=args.base_url, api_key="lm-studio")

    filas, por_plantilla = [], defaultdict(lambda: defaultdict(int))
    with psycopg.connect(DSN) as conn:
        for i, par in enumerate(pares, 1):
            sistema, pregunta, referencia = (m["content"] for m in par["messages"])
            if args.rag:
                sistema += "\n\nReglas aplicables a esta pregunta:\n" + reglas_para(pregunta)
            elif args.reglas:
                sistema += "\n\n" + (RAIZ / "reglas_legado.md").read_text(encoding="utf-8")
            r = cliente.chat.completions.create(
                model=args.modelo, temperature=0, max_tokens=8192,
                messages=[{"role": "system", "content": sistema}, {"role": "user", "content": pregunta}],
            )
            sql_modelo = extraer_sql(r.choices[0].message.content)
            terminacion = r.choices[0].finish_reason
            res_ref, _ = ejecutar(conn, referencia)
            if sql_modelo:
                res_mod, error = ejecutar(conn, sql_modelo)
            else:
                res_mod, error = None, f"sin SQL (finish_reason={terminacion})"

            ejecuta = res_mod is not None and len(res_mod) > 0
            coincide = ejecuta and res_mod == res_ref
            coincide_sql = normalizar_sql(sql_modelo) == normalizar_sql(referencia)
            pl = plantilla_de(pregunta)
            filas.append(dict(plantilla=pl, pregunta=pregunta, sql_modelo=sql_modelo,
                              sql_referencia=referencia, ejecuta=ejecuta,
                              coincide_resultado=coincide, coincide_sql=coincide_sql,
                              error=error))
            por_plantilla[pl]["n"] += 1
            por_plantilla[pl]["ejecuta"] += int(ejecuta)
            por_plantilla[pl]["coincide_resultado"] += int(coincide)
            print(f"[{i}/{len(pares)}] executes={ejecuta} matches={coincide} {pregunta[:70]}", flush=True)

    n = len(filas)
    resumen = dict(
        modelo=args.modelo, nombre=args.nombre, pares=n,
        ejecuta=round(sum(f["ejecuta"] for f in filas) / n, 3),
        coincide_resultado=round(sum(f["coincide_resultado"] for f in filas) / n, 3),
        coincide_sql=round(sum(f["coincide_sql"] for f in filas) / n, 3),
        por_plantilla={k: dict(v) for k, v in sorted(por_plantilla.items())},
    )
    salida = RAIZ / "resultados"
    salida.mkdir(exist_ok=True)
    with open(salida / f"{args.nombre}_detalle.jsonl", "w", encoding="utf-8") as f:
        for fila in filas:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    (salida / f"{args.nombre}_resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumen.items() if k != "por_plantilla"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
