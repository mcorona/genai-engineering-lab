"""Fails if any of the model's accuracies is below the threshold. Usage: python umbral.py 0.80"""
import json
import sys
from pathlib import Path

umbral = float(sys.argv[1])
resumenes = sorted(Path("semana-07/resultados").glob("resumen_*.json"))
if not resumenes:
    sys.exit("There is no summary of the run.")
filas = json.loads(resumenes[-1].read_text(encoding="utf-8"))
for f in filas:
    print(f"{f['modelo']} {f['idioma']} accuracy={f['exactitud']}")
malas = [f for f in filas if f["exactitud"] < umbral]
if malas:
    sys.exit(f"Below the threshold {umbral}: " + ", ".join(f"{f['modelo']}/{f['idioma']}" for f in malas))
print(f"All accuracies >= {umbral}")
