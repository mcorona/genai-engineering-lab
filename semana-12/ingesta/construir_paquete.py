"""Week 12, activity 2: the frozen ingestion package for the managed RAG services, with per-document permissions.

Document base = that of the in-house pipeline (the semana10.chunks index of week 10, activity 7) plus week 9's beta
tenant, which the cross-tenant leak tests need (activity 6):
- alfa: 24 text documents (semana-08/corpus) and 6 week 10 non-text documents in their original format
  (2 PDFs with tables, 2 JPG scans, 2 PNG images);
- beta: 10 documents (semana-09/corpus_beta), with the same names as in alfa and a different figure in the passage.
Permissions: roles per document from semana-09/datasets/permisos.json and semana-10/datasets/permisos_semana10.json (the
same as the assistant's); the tenant by folder.

Output in semana-12/ingesta/paquete/ (uploaded as is to S3 and GCS):
- administrado/<tenant>/<original file>: what each service parses, chunks and embeds with its native options;
- controlado/textos/<tenant>/<doc>.txt: the text the in-house pipeline indexes (pdfplumber for PDFs; Haiku's transcription
  and description for scans and images; the md as is);
- controlado/chunks/<tenant>/<doc>__NNN.txt: the in-house pipeline's chunks (fixed 400/80), one per file, to
  ingest them without re-chunking (Bedrock: chunking NONE);
- next to each file, <file>.metadata.json (the Bedrock Knowledge Bases format: metadataAttributes);
- vertex_<mode>.jsonl: documents for Vertex AI Search (id, structData with the same fields, content.uri in GCS);
- manifiesto.json: documents, permissions, the sha256 of each file and of the gold set, and the validations.
Metadata fields (the same in both services): tenant_id (text), roles (a list of text), source (the document name
without the extension, the one week 11's metrics use), doc_id (<tenant>__<source>), tipo and, for chunks, chunk.
Deterministic: running it twice gives the same files. No API calls and no cost.
"""
import hashlib
import json
import re
import shutil
import subprocess
import sys
import types
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
REPO = RAIZ.parent
SALIDA = AQUI / "paquete"
sys.modules.setdefault("psycopg", types.ModuleType("psycopg"))  # the assistant imports it; the database is not used here
sys.path.insert(0, str(REPO / "semana-10" / "experimentos"))
import asistente as a  # noqa: E402  (documentos(), trocear() and ROLES: those of the in-house pipeline)

# Bucket names from config.sh (the default prefix and project), so that the package and the scripts match.
_cfg = (RAIZ / "infra" / "config.sh").read_text()
PREFIJO = re.search(r"^PREFIJO=(\S+)", _cfg, re.M).group(1)
PROYECTO = re.search(r"^GCP_PROYECTO=\$\{GCP_PROYECTO:-([^}]+)\}", _cfg, re.M).group(1)
GCS = f"gs://{PREFIJO}-docs-{PROYECTO}"
ORIGINALES_NO_TEXTO = {"tarifas_flete": "semana-10/pdf/tarifas_flete.pdf", "matriz_proveedores": "semana-10/pdf/matriz_proveedores.pdf",
                       "acta_inventario_norte": "semana-10/escaneos/acta_inventario_norte_p1.jpg",
                       "remision_r4471": "semana-10/escaneos/remision_r4471_p1.jpg",
                       "grafica_nivel_servicio": "semana-10/imagenes/grafica_nivel_servicio.png",
                       "plano_cedis_occidente": "semana-10/imagenes/plano_cedis_occidente.png"}
MIME = {".md": "text/plain", ".txt": "text/plain", ".pdf": "application/pdf", ".jpg": "image/jpeg", ".png": "image/png"}
GOLDEN = ["semana-11/datasets/eval_rag_es.jsonl", "semana-11/datasets/eval_rag_en.jsonl",
          "semana-09/datasets/multitenant_es.jsonl", "semana-09/datasets/multitenant_en.jsonl"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git_blob(ruta):
    """The file's hash on main (or origin/main in CI); empty if there is no reference."""
    for ref in ("main", "origin/main"):
        r = subprocess.run(["git", "-C", str(REPO), "rev-parse", f"{ref}:{ruta}"], capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
    return ""


def escribir(ruta, contenido=None, origen=None, meta=None):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if origen is not None:
        shutil.copyfile(origen, ruta)
    else:
        ruta.write_text(contenido, encoding="utf-8")
    if meta is not None:
        Path(f"{ruta}.metadata.json").write_text(json.dumps({"metadataAttributes": meta}, ensure_ascii=False, indent=1) + "\n",
                                                 encoding="utf-8")


def main():
    if SALIDA.exists():
        shutil.rmtree(SALIDA)
    textos = {"alfa": a.documentos(),
              "beta": {p.stem: p.read_text(encoding="utf-8") for p in sorted((REPO / "semana-09" / "corpus_beta").glob("*.md"))}}
    docs, vertex = [], {"administrado": [], "controlado_textos": [], "controlado_chunks": []}
    for tenant, por_doc in textos.items():
        for stem, texto in sorted(por_doc.items()):
            roles = sorted(a.ROLES[stem])
            tipo = "texto" if stem not in ORIGINALES_NO_TEXTO or tenant != "alfa" else Path(ORIGINALES_NO_TEXTO[stem]).suffix[1:]
            base = {"tenant_id": tenant, "roles": roles, "source": stem, "doc_id": f"{tenant}__{stem}", "tipo": tipo}
            # managed: the original file
            origen = REPO / (ORIGINALES_NO_TEXTO[stem] if tipo != "texto" else
                             (f"semana-08/corpus/{stem}.md" if tenant == "alfa" else f"semana-09/corpus_beta/{stem}.md"))
            r_adm = SALIDA / "administrado" / tenant / origen.name
            escribir(r_adm, origen=origen, meta=base)
            vertex["administrado"].append({"id": base["doc_id"], "structData": base,
                                           "content": {"mimeType": MIME[origen.suffix], "uri": f"{GCS}/{r_adm.relative_to(SALIDA)}"}})
            # controlled: the extracted text and the in-house pipeline's chunks
            r_txt = SALIDA / "controlado" / "textos" / tenant / f"{stem}.txt"
            escribir(r_txt, contenido=texto, meta=base)
            vertex["controlado_textos"].append({"id": base["doc_id"], "structData": base,
                                                "content": {"mimeType": "text/plain", "uri": f"{GCS}/{r_txt.relative_to(SALIDA)}"}})
            chunks = a.trocear(texto, stem)
            for i, c in enumerate(chunks):
                meta = {**base, "doc_id": f"{tenant}__{stem}__{i:03d}", "chunk": i}
                r_ch = SALIDA / "controlado" / "chunks" / tenant / f"{stem}__{i:03d}.txt"
                escribir(r_ch, contenido=c, meta=meta)
                vertex["controlado_chunks"].append({"id": meta["doc_id"], "structData": meta,
                                                    "content": {"mimeType": "text/plain", "uri": f"{GCS}/{r_ch.relative_to(SALIDA)}"}})
            docs.append({**base, "original": str(origen.relative_to(REPO)), "chunks": len(chunks), "chars_texto": len(texto)})
    for modo, filas in vertex.items():
        (SALIDA / f"vertex_{modo}.jsonl").write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8")

    # ---------- validations ----------
    v = {}
    alfa = [d for d in docs if d["tenant_id"] == "alfa"]
    beta = [d for d in docs if d["tenant_id"] == "beta"]
    v["documentos"] = {"alfa": len(alfa), "beta": len(beta), "esperado": "30 y 10", "ok": len(alfa) == 30 and len(beta) == 10}
    v["chunks"] = {"alfa": sum(d["chunks"] for d in alfa), "beta": sum(d["chunks"] for d in beta),
                   "esperado_alfa": "68 (índice semana10.chunks)", "ok": sum(d["chunks"] for d in alfa) == 68}
    v["permisos"] = {"documentos_sin_roles": [d["doc_id"] for d in docs if not d["roles"]],
                     "roles_distintos": sorted({r for d in docs for r in d["roles"]})}
    v["permisos"]["ok"] = not v["permisos"]["documentos_sin_roles"]
    v["no_textuales_en_formato_original"] = {d["source"]: d["tipo"] for d in alfa if d["tipo"] != "texto"}
    copias = [(SALIDA / "administrado" / d["tenant_id"] / Path(d["original"]).name, REPO / d["original"]) for d in docs]
    v["originales_identicos"] = {"ok": all(sha(c) == sha(o) for c, o in copias), "n": len(copias)}
    # each reference passage of the week 11 gold set is intact in some chunk of its document (tenant alfa)
    chunks_alfa = {}
    for stem, t in textos["alfa"].items():
        chunks_alfa[stem] = a.trocear(t, stem)
    faltan, total = [], 0
    for ruta in GOLDEN[:2]:
        for l in (REPO / ruta).read_text(encoding="utf-8").splitlines():
            x = json.loads(l)
            for g in x["gold"]:
                total += 1
                s = Path(g["source"]).stem
                if not any(a.norm(g["passage"]) in a.norm(c) for c in chunks_alfa.get(s, [])):
                    faltan.append(f"{x['id']}/{x['lang']}")
    v["pasajes_golden_integros"] = {"total": total, "faltan": faltan, "ok": not faltan}
    faltan_mt, total_mt = [], 0
    chunks_beta = {stem: a.trocear(t, stem) for stem, t in textos["beta"].items()}
    for ruta in GOLDEN[2:]:
        for l in (REPO / ruta).read_text(encoding="utf-8").splitlines():
            x = json.loads(l)
            s = Path(x["source"]).stem
            for tenant, cs in (("alfa", chunks_alfa), ("beta", chunks_beta)):
                total_mt += 1
                if not any(a.norm(x["gold"][tenant]) in a.norm(c) for c in cs.get(s, [])):
                    faltan_mt.append(f"{x['id']}/{x['lang']}/{tenant}")
    v["pasajes_multitenant_integros"] = {"total": total_mt, "faltan": faltan_mt, "ok": not faltan_mt}
    gold = {}
    for ruta in GOLDEN:
        gold[ruta] = {"sha256": sha(REPO / ruta), "lineas": len((REPO / ruta).read_text(encoding="utf-8").splitlines()),
                      "sin_cambios_vs_main": git_blob(ruta) == subprocess.run(
                          ["git", "-C", str(REPO), "hash-object", ruta], capture_output=True, text=True).stdout.strip()}
    v["golden_sin_cambios"] = {"ok": all(g["sin_cambios_vs_main"] for g in gold.values())}
    ids = [f["id"] for fs in vertex.values() for f in fs]
    v["ids_vertex"] = {"unicos_por_modo": all(len({f['id'] for f in fs}) == len(fs) for fs in vertex.values()),
                       "max_longitud": max(map(len, ids)), "ok": max(map(len, ids)) <= 63}

    archivos = {str(p.relative_to(SALIDA)): sha(p) for p in sorted(SALIDA.rglob("*")) if p.is_file()}
    manifiesto = {"descripcion": "Paquete de ingesta de semana 12 (actividad 2). Ver construir_paquete.py.",
                  "gcs": GCS, "s3": f"s3://{PREFIJO}-docs-<cuenta de AWS>",
                  "campos_metadatos": {"tenant_id": "texto", "roles": "lista de texto", "source": "texto", "doc_id": "texto",
                                       "tipo": "texto", "chunk": "número (solo chunks)"},
                  "documentos": docs, "golden": gold, "validaciones": v,
                  "conteos": {"administrado": len(vertex["administrado"]), "controlado_textos": len(vertex["controlado_textos"]),
                              "controlado_chunks": len(vertex["controlado_chunks"]), "archivos": len(archivos) + 1},
                  "sha256_archivos": archivos}
    (SALIDA / "manifiesto.json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v[k] for k in v}, ensure_ascii=False, indent=1))
    print(json.dumps(manifiesto["conteos"]))
    if not all(x.get("ok", True) for x in v.values()):
        raise SystemExit("VALIDACIÓN FALLIDA")
    print("Valid package.")


if __name__ == "__main__":
    main()
