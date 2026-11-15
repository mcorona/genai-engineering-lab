"""Lightweight RAG: selects only the business rules relevant to each question.

The rules live in reglas_legado.md, numbered. Each rule has keywords; if the
question contains any of them, the rule goes into the prompt. Rule 12 (free text) always goes in.
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
REGLAS = {
    int(m.group(1)): m.group(2).strip()
    for m in re.finditer(r"^(\d+)\. (.+)$",
                         (RAIZ / "reglas_legado.md").read_text(encoding="utf-8"), flags=re.M)
}
SIEMPRE = [12]
PALABRAS = {
    1: ["factura", "ventas", "vigente", "válid", "vend", "cancel"],
    2: ["total", "monto", "suma", "iva", "importe", "precio", "costo", "cuánto", "cuanto"],
    3: ["fecha", "mes", "año", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
        "agosto", "septiembre", "octubre", "noviembre", "diciembre", "vacía", "cero"],
    4: ["moneda", "dólar", "dolar", "usd", "mxn", "agente", "divisa"],
    5: ["renglon", "líneas de la factura", "lineas de la factura", "productos y cantidades"],
    6: ["cliente", "activo", "activos", "producto", "línea", "linea"],
    7: ["sin cliente", "no existe", "registrado", "inexistente", "no está"],
    8: ["rfc"],
    9: ["almacén", "almacen", "existencia", "inventario"],
    10: ["costo", "artículo", "articulo", "unidad", "pieza", "caja", "factor"],
    11: ["salida", "entrada", "movimiento", "cancel", "cajas", "unidades base"],
}


def reglas_para(pregunta):
    texto = pregunta.lower()
    numeros = set(SIEMPRE)
    for num, palabras in PALABRAS.items():
        if any(p in texto for p in palabras):
            numeros.add(num)
    if re.search(r"\b200[1-9]\b", texto):
        numeros.add(3)
    return "\n".join(f"{n}. {REGLAS[n]}" for n in sorted(numeros) if n in REGLAS)
