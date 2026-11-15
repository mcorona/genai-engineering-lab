"""Builds the distillation (SFT) and DPO datasets from data/teacher.jsonl.

destilacion/train.jsonl: question -> the teacher's SQL, only where the teacher was right.
  The system prompt is the schema WITHOUT rules: the student learns to apply the rules without
  having them in the prompt (context distillation).

dpo/train.jsonl: prompt -> chosen (the validated reference SQL) and rejected (the teacher's SQL),
  only where the teacher was wrong and its SQL differs from the reference.

Usage:
    uv run python semana-04/entrenamiento/construir_datasets.py
"""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DATOS = RAIZ / "data"


def main():
    filas = [json.loads(l) for l in open(DATOS / "teacher.jsonl", encoding="utf-8")]
    reintento = DATOS / "teacher_reintento.jsonl"
    if reintento.exists():
        nuevas = {f["pregunta"]: f for f in (json.loads(l) for l in open(reintento, encoding="utf-8"))}
        filas = [nuevas.get(f["pregunta"], f) if not f["sql_maestro"] else f for f in filas]
    destilacion, dpo = [], []
    for f in filas:
        prompt = [{"role": "system", "content": f["sistema"]}, {"role": "user", "content": f["pregunta"]}]
        if f["coincide"] and f["sql_maestro"]:
            destilacion.append({"messages": prompt + [{"role": "assistant", "content": f["sql_maestro"]}]})
        if not f["coincide"] and f["sql_maestro"] and f["sql_maestro"] != f["referencia"]:
            dpo.append({
                "prompt": prompt,
                "chosen": [{"role": "assistant", "content": f["referencia"]}],
                "rejected": [{"role": "assistant", "content": f["sql_maestro"]}],
            })

    for nombre, datos in [("destilacion", destilacion), ("dpo", dpo)]:
        carpeta = RAIZ / nombre
        carpeta.mkdir(exist_ok=True)
        with open(carpeta / "train.jsonl", "w", encoding="utf-8") as fh:
            for d in datos:
                fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"questions: {len(filas)}")
    print(f"distillation (teacher right): {len(destilacion)}")
    print(f"DPO (teacher wrong, valid pair): {len(dpo)}")


if __name__ == "__main__":
    main()
