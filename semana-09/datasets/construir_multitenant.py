"""Builds the `beta` test tenant for activity 6 (multi-tenancy).

- corpus_beta/: 10 documents copied from the week 8 corpus (tenant `alfa`), identical except for
  the figure in the reference passage, which changes. That way the alfa and beta chunks are almost the same.
- datasets/multitenant_{es,en}.jsonl: one question per document, with alfa's passage and beta's.

It checks that each passage appears only once in its document and that, with fixed 400/80 chunking,
it stays complete within some chunk in both tenants.
"""
import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "semana-08" / "experimentos"))
from chunking_pasajes import ESTRATEGIAS  # noqa: E402

CORPUS_ALFA = R / "semana-08" / "corpus"
CORPUS_BETA = R / "semana-09" / "corpus_beta"
DS = R / "semana-09" / "datasets"
trocear = ESTRATEGIAS["fijo_400_solape_80"]

# base question id: (text that changes inside the passage, text in beta)
CAMBIOS = {
    "rec-01": ("30 días", "20 días"),
    "rec-04": ("98%", "95%"),
    "rec-07": ("Gerente de compras", "Director de compras"),
    "rec-11": ("1.5", "2.0"),
    "rec-15": ("95%", "90%"),
    "rec-19": ("4 horas", "8 horas"),
    "rec-24": ("20 unidades", "50 unidades"),
    "rec-30": ("40 horas", "24 horas"),
    "rec-33": ("45 días", "90 días"),
    "rec-40": ("14.50 MXN", "16.80 MXN"),
}

base = {lang: {d["id"]: d for d in map(json.loads, open(DS / f"avanzado_{lang}.jsonl", encoding="utf-8")) if d["tipo"] == "base"}
        for lang in ("es", "en")}

errores, docs_beta, salida = [], {}, {"es": [], "en": []}
for rid, (viejo, nuevo) in CAMBIOS.items():
    g = base["es"][rid]["gold"][0]
    fuente, p_alfa = g["source"], g["passage"]
    if p_alfa.count(viejo) != 1:
        errores.append(f"{rid}: '{viejo}' aparece {p_alfa.count(viejo)} veces en el pasaje")
        continue
    p_beta = p_alfa.replace(viejo, nuevo)
    texto_alfa = (CORPUS_ALFA / fuente).read_text(encoding="utf-8")
    if texto_alfa.count(p_alfa) != 1:
        errores.append(f"{rid}: el pasaje aparece {texto_alfa.count(p_alfa)} veces en {fuente}")
        continue
    if fuente in docs_beta:
        errores.append(f"{rid}: {fuente} ya se usó para otra pregunta")
        continue
    texto_beta = texto_alfa.replace(p_alfa, p_beta)
    docs_beta[fuente] = texto_beta
    if not any(p_alfa in c for c in trocear(texto_alfa, fuente)):
        errores.append(f"{rid}: pasaje de alfa partido por el chunking")
    if not any(p_beta in c for c in trocear(texto_beta, fuente)):
        errores.append(f"{rid}: pasaje de beta partido por el chunking")
    for lang in ("es", "en"):
        salida[lang].append({"id": f"mt-{rid}", "lang": lang, "question": base[lang][rid]["question"], "source": fuente,
                             "gold": {"alfa": p_alfa, "beta": p_beta}})

if errores:
    raise SystemExit("\n".join(errores))

CORPUS_BETA.mkdir(parents=True, exist_ok=True)
for nombre, texto in docs_beta.items():
    (CORPUS_BETA / nombre).write_text(texto, encoding="utf-8")
for lang, items in salida.items():
    with open(DS / f"multitenant_{lang}.jsonl", "w", encoding="utf-8") as f:
        for x in items:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
n_chunks = sum(len(trocear(t, n)) for n, t in docs_beta.items())
print(f"beta: {len(docs_beta)} documents, {n_chunks} chunks; {len(salida['es'])} questions per language; validation OK")
