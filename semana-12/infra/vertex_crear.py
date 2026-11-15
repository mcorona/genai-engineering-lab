"""Week 12, activity 5: Vertex AI Search (Agent Search) data stores and apps, with the semana12-operador service account
through impersonation. Requires gcp_crear.sh and gcp_bucket_crear.sh (the project owner) and the activity 2 package.

Two unstructured data stores in `global`, with the same metadata as Bedrock (tenant_id, roles, source, doc_id,
tipo) declared filterable in the schema before importing:
- vx-adm (managed mode): the originals, parsed and chunked by the service with the layout parser and the default
  chunking (500 tokens). Vertex does not accept Markdown or loose images as documents: the layout parser reads HTML,
  PDF, DOCX, PPTX and XLSX (not TXT) and does not import JPG or PNG. As a client would, the .md files are converted to HTML
  and the JPG and PNG files to a one-page PDF (the layout parser does OCR), without changing their content.
- vx-ctl (controlled mode): the 101 chunks of the in-house pipeline, one .txt document per chunk, without re-chunking (digital
  parser, no chunking): it isolates the quality of the index and the ranking.
Each data store has its search app (Enterprise edition, no LLM add-on). Ids in estado_gcp.json (outside Git).
Idempotent: it reuses whatever already exists by id.
"""
import html
import io
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PAQUETE = AQUI.parent / "ingesta" / "paquete"
CFG = (AQUI / "config.sh").read_text()
PREFIJO = re.search(r"^PREFIJO=(\S+)", CFG, re.M).group(1)
PROYECTO = re.search(r"^GCP_PROYECTO=\$\{GCP_PROYECTO:-([^}]+)\}", CFG, re.M).group(1)
UBICACION = "global"
BUCKET = f"{PREFIJO}-docs-{PROYECTO}"
SA = f"{PREFIJO}-operador@{PROYECTO}.iam.gserviceaccount.com"
API = f"https://discoveryengine.googleapis.com/v1/projects/{PROYECTO}/locations/{UBICACION}/collections/default_collection"
ESTADO = AQUI / "estado_gcp.json"
ESQUEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "properties": {
    "tenant_id": {"type": "string", "indexable": True, "retrievable": True},
    "roles": {"type": "array", "items": {"type": "string", "indexable": True, "retrievable": True}},
    "source": {"type": "string", "indexable": True, "retrievable": True},
    "doc_id": {"type": "string", "retrievable": True},
    "tipo": {"type": "string", "indexable": True, "retrievable": True},
    "chunk": {"type": "number", "retrievable": True}}}
STORES = {
    "vx-adm": {"jsonl": "vertex_vx-adm.jsonl", "procesamiento": {
        "chunkingConfig": {"layoutBasedChunkingConfig": {"chunkSize": 500, "includeAncestorHeadings": False}},
        "defaultParsingConfig": {"layoutParsingConfig": {}}}},
    "vx-ctl": {"jsonl": "vertex_controlado_chunks.jsonl", "procesamiento": {"defaultParsingConfig": {"digitalParsingConfig": {}}}},
}


def token():
    r = subprocess.run(["gcloud", "auth", "print-access-token", f"--impersonate-service-account={SA}"],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"Could not impersonate {SA}: {r.stderr.strip()[-300:]}")
    return r.stdout.strip()


def api(metodo, url, cuerpo=None, ok404=False):
    req = urllib.request.Request(url, method=metodo, data=None if cuerpo is None else json.dumps(cuerpo).encode(),
                                 headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json",
                                          "x-goog-user-project": PROYECTO})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            t = r.read()
            return json.loads(t) if t else {}
    except urllib.error.HTTPError as e:
        if ok404 and e.code == 404:
            return None
        raise SystemExit(f"{metodo} {url.split('/v1/')[-1]}: HTTP {e.code} {e.read().decode()[:600]}")


def esperar(op, que):
    t0 = time.time()
    while not op.get("done"):
        time.sleep(15)
        op = api("GET", f"https://discoveryengine.googleapis.com/v1/{op['name']}")
        print(f"  {que}: {int(time.time() - t0)} s", flush=True)
    if "error" in op:
        raise SystemExit(f"{que}: {op['error']}")
    return op, int(time.time() - t0)


# ---------- format conversion for the managed mode ----------

def md_a_html(md, titulo):
    """The corpus Markdown (headings, lists, tables, bold) to simple HTML, without changing the text."""
    linea = lambda s: re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(s))  # noqa: E731
    out, i, ls = [f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(titulo)}</title></head><body>"], 0, md.splitlines()
    while i < len(ls):
        s = ls[i].rstrip()
        if s.startswith("|"):
            filas = []
            while i < len(ls) and ls[i].strip().startswith("|"):
                celdas = [c.strip() for c in ls[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in celdas):
                    filas.append(celdas)
                i += 1
            out.append("<table>" + "".join("<tr>" + "".join(f"<{'th' if j == 0 else 'td'}>{linea(c)}</{'th' if j == 0 else 'td'}>"
                                                              for c in f) + "</tr>" for j, f in enumerate(filas)) + "</table>")
            continue
        m = re.match(r"(#{1,6})\s+(.*)", s)
        if m:
            out.append(f"<h{len(m.group(1))}>{linea(m.group(2))}</h{len(m.group(1))}>")
        elif re.match(r"\s*([-*]|\d+\.)\s+", s):
            items = []
            while i < len(ls) and re.match(r"\s*([-*]|\d+\.)\s+", ls[i]):
                items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", ls[i]))
                i += 1
            out.append("<ul>" + "".join(f"<li>{linea(x)}</li>" for x in items) + "</ul>")
            continue
        elif s.startswith(">"):
            out.append(f"<blockquote>{linea(s.lstrip('> '))}</blockquote>")
        elif s:
            out.append(f"<p>{linea(s)}</p>")
        i += 1
    return "\n".join(out + ["</body></html>"])


def preparar_administrado(tmp):
    """Converts and lists the vx-adm documents: (local path, GCS object, JSONL entry)."""
    from PIL import Image
    filas = []
    for l in (PAQUETE / "vertex_administrado.jsonl").read_text(encoding="utf-8").splitlines():
        d = json.loads(l)
        rel = d["content"]["uri"].split(f"gs://{BUCKET}/", 1)[1]
        orig = PAQUETE / rel
        if orig.suffix == ".md":
            dest, mime = tmp / "vx-adm" / Path(rel).with_suffix(".html"), "text/html"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(md_a_html(orig.read_text(encoding="utf-8"), d["structData"]["source"]), encoding="utf-8")
        elif orig.suffix in (".jpg", ".png"):
            dest, mime = tmp / "vx-adm" / Path(rel).with_suffix(".pdf"), "application/pdf"
            dest.parent.mkdir(parents=True, exist_ok=True)
            Image.open(orig).convert("RGB").save(dest, "PDF", resolution=150)
        else:
            dest, mime = tmp / "vx-adm" / rel, d["content"]["mimeType"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(orig.read_bytes())
        obj = f"vx-adm/{dest.relative_to(tmp / 'vx-adm')}"
        filas.append({**d, "content": {"mimeType": mime, "uri": f"gs://{BUCKET}/{obj}"}})
    (tmp / "vertex_vx-adm.jsonl").write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8")
    return filas


def subir(tmp):
    imp = [f"--impersonate-service-account={SA}"]
    subprocess.run(["gcloud", "storage", "rsync", "--recursive", "--delete-unmatched-destination-objects", str(PAQUETE / "controlado"),
                    f"gs://{BUCKET}/controlado", *imp, "--quiet"], check=True)
    subprocess.run(["gcloud", "storage", "rsync", "--recursive", "--delete-unmatched-destination-objects", str(tmp / "vx-adm"),
                    f"gs://{BUCKET}/vx-adm", *imp, "--quiet"], check=True)
    subprocess.run(["gcloud", "storage", "cp", str(PAQUETE / "vertex_controlado_chunks.jsonl"), str(tmp / "vertex_vx-adm.jsonl"),
                    f"gs://{BUCKET}/", *imp, "--quiet"], check=True)


def main():
    stores = sys.argv[1:] or list(STORES)
    estado = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        n = preparar_administrado(tmp)
        print(f"vx-adm: {len(n)} documents ({sum(f['content']['mimeType'] == 'text/html' for f in n)} md→HTML, "
              f"{sum(Path(f['content']['uri']).suffix == '.pdf' for f in n)} PDF, 4 of them converted images)")
        subir(tmp)
        print(f"uploaded to gs://{BUCKET}/ (controlado/, vx-adm/ and the JSONL files)")
    for sid in stores:
        ds_id, cfg = f"{PREFIJO}-{sid}", STORES[sid]
        ds = api("GET", f"{API}/dataStores/{ds_id}", ok404=True)
        if ds is None:
            op = api("POST", f"{API}/dataStores?dataStoreId={ds_id}", {
                "displayName": ds_id, "industryVertical": "GENERIC", "solutionTypes": ["SOLUTION_TYPE_SEARCH"],
                "contentConfig": "CONTENT_REQUIRED", "documentProcessingConfig": cfg["procesamiento"]})
            esperar(op, f"crear data store {ds_id}")
            print(f"data store {ds_id}: created")
        op = api("PATCH", f"{API}/dataStores/{ds_id}/schemas/default_schema", {"jsonSchema": json.dumps(ESQUEMA)})
        if op and not op.get("done", True):
            esperar(op, f"esquema {ds_id}")
        print(f"data store {ds_id}: schema with filterable tenant_id and roles")
        op = api("POST", f"{API}/dataStores/{ds_id}/branches/0/documents:import", {
            "gcsSource": {"inputUris": [f"gs://{BUCKET}/{cfg['jsonl']}"], "dataSchema": "document"},
            "reconciliationMode": "FULL"})
        op, seg = esperar(op, f"importar {ds_id}")
        meta = op.get("metadata", {})
        errores = op.get("response", {}).get("errorSamples", [])
        print(f"import {ds_id}: {meta.get('successCount', 0)} successes, {meta.get('failureCount', 0)} failures, {seg} s")
        for e in errores[:8]:
            print("   failure:", str(e.get("message", e))[:300])
        eng_id = f"{ds_id}-app"
        if api("GET", f"{API}/engines/{eng_id}", ok404=True) is None:
            op = api("POST", f"{API}/engines?engineId={eng_id}", {
                "displayName": eng_id, "solutionType": "SOLUTION_TYPE_SEARCH", "industryVertical": "GENERIC",
                "dataStoreIds": [ds_id], "searchEngineConfig": {"searchTier": "SEARCH_TIER_ENTERPRISE", "searchAddOns": []}})
            esperar(op, f"crear app {eng_id}")
            print(f"app {eng_id}: created (Enterprise, no LLM add-on)")
        estado[sid] = {"data_store": ds_id, "engine": eng_id, "importados": int(meta.get("successCount", 0)),
                       "fallidos": int(meta.get("failureCount", 0)), "importacion_s": seg}
        ESTADO.write_text(json.dumps(estado, indent=1))
    print(json.dumps(estado, indent=1))


if __name__ == "__main__":
    main()
