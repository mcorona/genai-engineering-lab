"""Week 11, activity 1: the frozen RAG evaluation gold set (ES/EN).

Composition per language (75 questions):
- base (50): the week 8/9 questions (semana-08/datasets/recuperacion_{es,en}.jsonl), with their literal passages.
  The 15 document questions of the week 10 integrated gold set come from this same set (field `origen`), so they are
  already here; they are not duplicated.
- no_textual (15): the week 10 ones (5 PDF, 5 OCR and 5 image). Their `gold` is the exact answer and the source
  document (the evidence in the index is a chunk of that document that contains the answer, as in week 10).
- sin_respuesta (10): questions from the same domain whose answer is not in the corpus. The correct answer is to say it
  is not in the documents. It checks that their key terms appear neither in the week 8 corpus nor in the week 10 sources.

Reference answer (`referencia`): Haiku 5.5 low writes it using only the passage (or the source document and the
exact answer, for non-text questions), in the question's language, in one or two sentences. Automatic validation:
every figure in the reference appears in the passage (or in the document line that contains it), the source or the question;
no reference of an answerable question says there is no answer; and for non-text questions the exact answer appears in the
reference. The model's answers are saved in resultados/referencias_cache.json (reused when rebuilding).
A sample for manual review: 20 answerable questions (10 per language, seed 11) in resultados/revision_referencias.md.

Output: datasets/eval_rag_{es,en}.jsonl with id, lang, tipo, question, gold, referencia, respondible and origen.
Requires ANTHROPIC_API_KEY (only for the references that are not in the cache).
"""
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REPO = RAIZ.parent
CORPUS = REPO / "semana-08" / "corpus"
FUENTES10 = REPO / "semana-10" / "fuentes"
RES = RAIZ / "resultados"
CACHE = RES / "referencias_cache.json"
PRECIOS = json.loads((REPO / "semana-07" / "prices.json").read_text(encoding="utf-8"))
MODELO = "claude-haiku-5-5"

SISTEMA = ("Redactas la respuesta de referencia de un conjunto de evaluación. Recibes el documento completo, solo para "
           "entender el contexto (por ejemplo, los encabezados de una tabla), y el pasaje de referencia. Responde la "
           "pregunta con la información del PASAJE: no agregues datos, condiciones ni ejemplos que no estén en él. "
           "El pasaje siempre contiene la respuesta. Una o dos "
           "oraciones completas y directas, en el idioma de la pregunta. Conserva cifras, unidades y nombres exactamente "
           "como aparecen. Si el texto está en español y la pregunta en inglés, traduce la respuesta pero no las cifras. "
           "Escribe solo la respuesta, sin comillas ni preámbulo.")

# (id, ES, EN, terms that must not appear in the corpus)
SIN_RESPUESTA = [
    ("nr-01", "¿Cuántos días de vacaciones tiene un empleado de almacén en su primer año?",
     "How many vacation days does a warehouse employee get in their first year?", ["vacacion"]),
    ("nr-02", "¿Qué aseguradora cubre la mercancía en tránsito entre CEDIS?",
     "Which insurer covers goods in transit between distribution centers?", ["asegurador", "seguro de"]),
    ("nr-03", "¿Qué software contable usa el área de finanzas?",
     "Which accounting software does the finance department use?", ["contab"]),
    ("nr-04", "¿Qué interés moratorio se cobra a un cliente que paga tarde?",
     "What late-payment interest is charged to a customer who pays late?", ["interés", "moratori"]),
    ("nr-05", "¿Quién es el director general de la empresa?",
     "Who is the company's chief executive officer?", ["director general"]),
    ("nr-06", "¿Cuál es la política de trabajo remoto para los compradores?",
     "What is the remote work policy for buyers?", ["trabajo remoto", "home office"]),
    ("nr-07", "¿De cuánto es el aguinaldo de los empleados?",
     "How much is the employees' year-end bonus?", ["aguinaldo"]),
    ("nr-08", "¿Cada cuánto se entrega uniforme al personal de almacén?",
     "How often are uniforms issued to warehouse staff?", ["uniforme"]),
    ("nr-09", "¿Qué comisión cobra la empresa por factoraje a proveedores?",
     "What fee does the company charge suppliers for factoring?", ["factoraje"]),
    ("nr-10", "¿Qué pasa con los pedidos de clientes durante una huelga de transportistas?",
     "What happens to customer orders during a carriers' strike?", ["huelga"]),
]
NEGATIVA = re.compile(r"\bno (hay|contiene|se (indica|menciona|especifica))\b|\bno est[aá] en\b|cannot be answered|does not (contain|say|specify|mention)|not (in|mentioned in) the", re.I)
NO_ESTA = {"es": "La información no está en los documentos.", "en": "The information is not in the documents."}


def llamar(contenido):
    cuerpo = {"model": MODELO, "max_tokens": 2000, "system": SISTEMA, "output_config": {"effort": "low"},
              "messages": [{"role": "user", "content": contenido}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(cuerpo).encode(),
                                 headers={"content-type": "application/json", "anthropic-version": "2023-06-01",
                                          "x-api-key": os.environ["ANTHROPIC_API_KEY"]})
    for intento in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and intento < 3:
                time.sleep(2 ** (intento + 1))
                continue
            raise SystemExit(f"API HTTP {e.code}: {e.read().decode()[:300]}")
    if d.get("stop_reason") == "max_tokens":
        raise SystemExit("Output truncated by max_tokens.")
    u, p = d["usage"], PRECIOS[f"anthropic:{MODELO}"]
    texto = "".join(b.get("text", "") for b in d["content"] if b.get("type") == "text").strip()
    return {"texto": texto, "tokens_in": u["input_tokens"], "tokens_out": u["output_tokens"],
            "costo_usd": (u["input_tokens"] * p["in"] + u["output_tokens"] * p["out"]) / 1e6}


def cifras(t):
    t = re.sub(r"(\d+)\s*(mil|thousand)\b", lambda m: m.group(1) + "000", t)  # "300 mil" -> 300000
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", t)}


def lineas_con(doc, pasaje):
    """The full document lines that contain the passage (or its start, if the passage spans lines)."""
    inicio = pasaje.strip().splitlines()[0][:40]
    return "\n".join(l for l in doc.splitlines() if inicio in l)


def norm(t):
    return " ".join(t.replace("**", "").lower().split())


def main():
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    corpus = "\n".join(p.read_text(encoding="utf-8") for p in CORPUS.glob("*.md")) + "\n" + \
             "\n".join(p.read_text(encoding="utf-8") for p in FUENTES10.glob("*.*") if p.is_file())
    errores, salida, costo_nuevo = [], {"es": [], "en": []}, 0.0
    for lang in ("es", "en"):
        base = [json.loads(l) for l in (REPO / "semana-08" / "datasets" / f"recuperacion_{lang}.jsonl").read_text(encoding="utf-8").splitlines()]
        integ = [json.loads(l) for l in (REPO / "semana-10" / "datasets" / f"integrado_{lang}.jsonl").read_text(encoding="utf-8").splitlines()]
        ids_base = {x["id"] for x in base}
        dup = [x["origen"] for x in integ if x["tipo"] == "documental"]
        if not set(dup) <= ids_base:
            errores.append(f"{lang}: documentales de semana 10 que no están en semana 8: {sorted(set(dup) - ids_base)}")
        items = []
        for x in base:
            texto = "\n".join(g["passage"] for g in x["gold"])
            docs = "\n\n".join((CORPUS / s).read_text(encoding="utf-8") for s in dict.fromkeys(g["source"] for g in x["gold"]))
            items.append({"id": x["id"], "lang": lang, "tipo": "base", "question": x["question"], "gold": x["gold"],
                          "respondible": True, "origen": "semana-08/datasets/recuperacion",
                          "_contenido": f"Documento:\n{docs}\n\nPasaje de referencia:\n{texto}\n\nPregunta: {x['question']}",
                          # To validate figures: the passage plus the full document line that contains it (for example,
                          # the "Nivel 2" at the start of the line, which the literal passage omits).
                          "_fuente": texto + "\n" + "\n".join(lineas_con((CORPUS / g["source"]).read_text(encoding="utf-8"), g["passage"]) for g in x["gold"])})
        for x in integ:
            if x["tipo"] != "no_textual":
                continue
            doc = (FUENTES10 / x["fuente"]).read_text(encoding="utf-8")
            items.append({"id": x["id"], "lang": lang, "tipo": f"no_textual/{x['formato']}", "question": x["question"],
                          "gold": [{"source": x["fuente"], "passage": x["respuesta"]}], "respondible": True,
                          "origen": "semana-10/datasets/integrado",
                          "_contenido": f"Documento:\n{doc}\n\nPasaje de referencia (respuesta exacta): {x['respuesta']}\n\nPregunta: {x['question']}",
                          "_fuente": doc, "_respuesta": x["respuesta"]})
        for i, es, en, terminos in SIN_RESPUESTA:
            hallados = [t for t in terminos if t.lower() in corpus.lower()]
            if hallados:
                errores.append(f"{i}: términos presentes en el corpus: {hallados}")
            items.append({"id": i, "lang": lang, "tipo": "sin_respuesta", "question": es if lang == "es" else en,
                          "gold": [], "referencia": NO_ESTA[lang], "respondible": False, "origen": "semana-11"})
        for x in items:
            if not x["respondible"]:
                continue
            k = f"v2::{x['id']}::{lang}"  # v2: with the document as context (v1 misread the table row of rec-07)
            if k not in cache:
                cache[k] = llamar(x["_contenido"])
                costo_nuevo += cache[k]["costo_usd"]
                CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            x["referencia"] = cache[k]["texto"]
            extra = cifras(x["referencia"]) - cifras(x["_fuente"]) - cifras(x["question"])  # the question can carry figures
            if extra:
                errores.append(f"{x['id']} {lang}: cifras de la referencia que no están en el texto: {sorted(extra)}")
            if x.get("_respuesta") and not cifras(x["_respuesta"]) <= cifras(x["referencia"]) | {""}:
                errores.append(f"{x['id']} {lang}: la referencia no trae la cifra de la respuesta exacta '{x['_respuesta']}'")
            if NEGATIVA.search(x["referencia"]):
                errores.append(f"{x['id']} {lang}: la referencia dice que no hay respuesta, pero la pregunta es respondible")
            if x.get("_respuesta") and not cifras(x["_respuesta"]) and lang == "es" and norm(x["_respuesta"]) not in norm(x["referencia"]):
                errores.append(f"{x['id']} {lang}: la referencia no contiene la respuesta exacta '{x['_respuesta']}'")
        salida[lang] = [{k: v for k, v in x.items() if not k.startswith("_")} for x in items]

    for lang, filas in salida.items():
        (RAIZ / "datasets" / f"eval_rag_{lang}.jsonl").write_text(
            "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in filas), encoding="utf-8")
    muestra = []
    rnd = random.Random(11)
    for lang in ("es", "en"):
        muestra += rnd.sample([x for x in salida[lang] if x["respondible"]], 10)
    lineas = ["# Revisión manual de referencias (muestra de 20, semilla 11)", "",
              "Criterio: la referencia responde la pregunta, usa solo el pasaje y no agrega ni cambia datos.", "",
              "| # | Id | Idioma | Pregunta | Pasaje o respuesta exacta | Referencia | Veredicto |", "|---|---|---|---|---|---|---|"]
    for n, x in enumerate(muestra, 1):
        pas = " / ".join(g["passage"] for g in x["gold"]).replace("|", "\\|").replace("\n", " ")
        lineas.append(f"| {n} | {x['id']} | {x['lang']} | {x['question']} | {pas} | {x['referencia'].replace('|', '/')} | |")
    (RES / "revision_referencias.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    total = sum(v["costo_usd"] for v in cache.values())
    for lang in ("es", "en"):
        f = salida[lang]
        print(f"{lang}: {len(f)} questions (base {sum(x['tipo'] == 'base' for x in f)}, "
              f"non-text {sum(x['tipo'].startswith('no_textual') for x in f)}, unanswerable {sum(not x['respondible'] for x in f)})")
    print(f"References: cost of this run ${costo_nuevo:.4f}; total in the cache ${total:.4f}")
    if errores:
        print("VALIDACIÓN CON OBSERVACIONES:\n- " + "\n- ".join(errores))
        sys.exit(1)
    print("Validation OK.")


if __name__ == "__main__":
    main()
