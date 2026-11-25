"""Week 12, activity 6: leaks by role and across tenants in the managed RAG services, with the week 10 tests.

Cases (the same as week 10, activity 8):
- role: each document or non-text question of the week 10 integrated gold set (15 + 15 per language) whose reference
  document is not open to every role; a user of the alfa tenant with a single role WITHOUT access to that document (the
  first one, in week 10's order, that is not among its roles);
- tenant: the 10 week 9 multi-tenant questions per language (their documents exist in alfa and in beta with different
  figures), with an alfa user and a beta user, both with every role.
Systems: the 4 Bedrock Knowledge Bases (Retrieve), RetrieveAndGenerate over adm-fijo-bda (the adopted managed option;
the cited references are checked) and the 2 Vertex AI Search data stores (hybrid search), with the tenant and role
filter inside the query and top 20.
Leak = a chunk in the results whose real tenant or roles do not authorize the user. The tenant and the document are taken
from the file's location (not from the metadata the service returns) and the document's roles from the ingestion
package's manifest (activity 2). The cases in which the forbidden reference document appears are also counted.
Control: the same queries WITHOUT a filter on one KB and one data store; unauthorized chunks must appear, which shows
that the test detects the leak when there is no filter. It also records how many results each filtered query returns:
if the filter were applied after the top k, users with a single role would get fewer than 20.
Output: resultados/seguridad.md (written by hand from this data), seguridad_resumen.json and seguridad_detalle.csv.
Cost: Retrieve and Vertex search (cents); RetrieveAndGenerate with Haiku 4.5 (≈ $0.17).
"""
import csv
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import suites as s  # noqa: E402  (Bedrock and Vertex helpers, the gold set and the assistant)

a, RAIZ, REPO = s.a, s.RAIZ, s.REPO
ORDEN_ROLES = ["ventas", "calidad", "compras", "almacen", "finanzas", "operaciones"]  # week 10, seguridad.py
TODOS = sorted({r for rs in a.ROLES.values() for r in rs})
MANIF = json.loads((RAIZ / "ingesta" / "paquete" / "manifiesto.json").read_text(encoding="utf-8"))
ROLES_DOC = {(d["tenant_id"], d["source"]): set(d["roles"]) for d in MANIF["documentos"]}
RES = RAIZ / "resultados"


def casos():
    out = []
    for lang in ("es", "en"):
        for l in (REPO / "semana-10" / "datasets" / f"integrado_{lang}.jsonl").read_text(encoding="utf-8").splitlines():
            x = json.loads(l)
            if x["tipo"] not in ("documental", "no_textual"):
                continue
            fuente = Path(x["gold"][0]["source"] if x.get("gold") else x["fuente"]).stem
            libre = [r for r in ORDEN_ROLES if r not in a.ROLES[fuente]]
            if libre:
                out.append({"tipo": "rol", "id": x["id"], "lang": lang, "question": x["question"], "fuente": fuente,
                            "usuario": {"tenant": "alfa", "roles": [libre[0]]}})
        for l in (REPO / "semana-09" / "datasets" / f"multitenant_{lang}.jsonl").read_text(encoding="utf-8").splitlines():
            x = json.loads(l)
            for t in ("alfa", "beta"):
                out.append({"tipo": "tenant", "id": x["id"], "lang": lang, "question": x["question"],
                            "fuente": Path(x["source"]).stem, "usuario": {"tenant": t, "roles": TODOS}})
    return out


def autorizado(tenant, source, u):
    return tenant == u["tenant"] and bool(ROLES_DOC.get((tenant, source), set()) & set(u["roles"]))


def filtro_bedrock(u):
    roles = [{"listContains": {"key": "roles", "value": r}} for r in u["roles"]]
    return {"andAll": [{"equals": {"key": "tenant_id", "value": u["tenant"]}}, roles[0] if len(roles) == 1 else {"orAll": roles}]}


def filtro_vertex(u):
    return f'tenant_id: ANY("{u["tenant"]}") AND roles: ANY(' + ",".join(f'"{r}"' for r in u["roles"]) + ")"


def ubicacion_s3(uri):
    """s3://<bucket>/administrado/<tenant>/<archivo> o .../controlado/chunks/<tenant>/<doc>__NNN.txt"""
    partes = uri.split("/")
    stem = Path(partes[-1]).stem.removesuffix("_p1")
    return partes[-2], stem.split("__")[0]


def bedrock(config, c, con_filtro=True, cli=None):
    vsc = {"numberOfResults": 20}
    if con_filtro:
        vsc["filter"] = filtro_bedrock(c["usuario"])
    r = cli.retrieve(knowledgeBaseId=s._kb(config), retrievalQuery={"text": c["question"]},
                     retrievalConfiguration={"vectorSearchConfiguration": vsc})
    return [ubicacion_s3(z.get("location", {}).get("s3Location", {}).get("uri", "")) for z in r["retrievalResults"]]


def bedrock_rag(config, c, cli, modelo):
    r = cli.retrieve_and_generate(input={"text": c["question"]}, retrieveAndGenerateConfiguration={
        "type": "KNOWLEDGE_BASE", "knowledgeBaseConfiguration": {"knowledgeBaseId": s._kb(config), "modelArn": modelo,
            "retrievalConfiguration": {"vectorSearchConfiguration": {"numberOfResults": 5, "filter": filtro_bedrock(c["usuario"])}}}})
    return [ubicacion_s3(ref.get("location", {}).get("s3Location", {}).get("uri", ""))
            for cit in r.get("citations", []) for ref in cit.get("retrievedReferences", [])]


def vertex(store, c, con_filtro=True):
    proy, _ = s._vx_conf()
    ruta = RAIZ / "infra" / "estado_gcp.json"
    estado = json.loads(ruta.read_text(encoding="utf-8"))[store] if ruta.exists() else {"engine": f"semana12-{store}-app"}
    url = (f"https://discoveryengine.googleapis.com/v1/projects/{proy}/locations/global/collections/default_collection/"
           f"engines/{estado['engine']}/servingConfigs/default_search:search")
    cuerpo = {"query": c["question"], "pageSize": 20, "relevanceThreshold": "LOWEST", "queryExpansionSpec": {"condition": "AUTO"},
              "contentSearchSpec": {"searchResultMode": "CHUNKS" if store == "vx-adm" else "DOCUMENTS"}}
    if con_filtro:
        cuerpo["filter"] = filtro_vertex(c["usuario"])
    out = []
    for z in s._vx(url, cuerpo).get("results", []):
        if "chunk" in z:
            partes = z["chunk"].get("documentMetadata", {}).get("uri", "").split("/")
            out.append((partes[-2], Path(partes[-1]).stem.removesuffix("_p1")))
        else:
            t, stem, _ = z["document"]["id"].split("__")
            out.append((t, stem))
    return out


def medir(nombre, fn, cs, hilos=1):
    def uno(c):
        t0 = time.perf_counter()
        res = fn(c)
        no_aut = [(t, src) for t, src in res if not autorizado(t, src, c["usuario"])]
        return {"sistema": nombre, "tipo": c["tipo"], "id": c["id"], "lang": c["lang"], "usuario": json.dumps(c["usuario"]),
                "resultados": len(res), "no_autorizados": len(no_aut),
                "documento_prohibido": int(c["tipo"] == "rol" and any(src == c["fuente"] for _, src in res)
                                           or c["tipo"] == "tenant" and any(t != c["usuario"]["tenant"] for t, _ in res)),
                "ejemplo": "; ".join(f"{t}/{src}" for t, src in no_aut[:3]), "lat": round(time.perf_counter() - t0, 3)}
    with ThreadPoolExecutor(hilos) as ex:
        filas = list(ex.map(uno, cs))
    print(f"{nombre}: {sum(f['no_autorizados'] for f in filas)} unauthorized chunks in {len(filas)} queries", flush=True)
    return filas


def main():
    cs = casos()
    print(f"cases: {sum(c['tipo'] == 'rol' for c in cs)} by role, {sum(c['tipo'] == 'tenant' for c in cs)} across tenants")
    cli = s._aws("bedrock-agent-runtime")
    cuenta = s._aws("sts").get_caller_identity()["Account"]
    modelo = f"arn:aws:bedrock:us-east-1:{cuenta}:inference-profile/{s.PERFIL_RAG}"
    filas = []
    for cfg in ("adm-pred", "adm-fijo", "adm-fijo-bda", "ctl-chunks"):
        filas += medir(f"bedrock {cfg}", lambda c, cfg=cfg: bedrock(cfg, c, True, cli), cs)
    filas += medir("bedrock adm-fijo-bda RetrieveAndGenerate", lambda c: bedrock_rag("adm-fijo-bda", c, cli, modelo), cs, hilos=4)
    for st in ("vx-adm", "vx-ctl"):
        filas += medir(f"vertex {st}", lambda c, st=st: vertex(st, c, True), cs)
    control = medir("CONTROL bedrock ctl-chunks sin filtro", lambda c: bedrock("ctl-chunks", c, False, cli), cs)
    control += medir("CONTROL vertex vx-ctl sin filtro", lambda c: vertex("vx-ctl", c, False), cs)

    resumen = {"casos": {"rol": sum(c["tipo"] == "rol" for c in cs), "tenant": sum(c["tipo"] == "tenant" for c in cs)},
               "sistemas": {}, "control_sin_filtro": {}}
    for destino, fs in (("sistemas", filas), ("control_sin_filtro", control)):
        for nombre in dict.fromkeys(f["sistema"] for f in fs):
            g = [f for f in fs if f["sistema"] == nombre]
            resumen[destino][nombre] = {
                tipo: {"consultas": len(h), "chunks_no_autorizados": sum(f["no_autorizados"] for f in h),
                       "consultas_con_fuga": sum(1 for f in h if f["no_autorizados"]),
                       "documento_prohibido": sum(f["documento_prohibido"] for f in h),
                       "resultados_media": round(statistics.mean(f["resultados"] for f in h), 1),
                       "resultados_min": min(f["resultados"] for f in h)}
                for tipo in ("rol", "tenant") for h in [[f for f in g if f["tipo"] == tipo]]}
    resumen["fuga_total"] = sum(v[t]["chunks_no_autorizados"] for v in resumen["sistemas"].values() for t in ("rol", "tenant"))
    (RES / "seguridad_resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (RES / "seguridad_detalle.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas + control)
    print("\n| System | Type | Queries | Unauthorized chunks | Queries with a leak | Forbidden doc. | Results (mean / min) |")
    print("|---|---|---|---|---|---|---|")
    for destino in ("sistemas", "control_sin_filtro"):
        for nombre, v in resumen[destino].items():
            for t in ("rol", "tenant"):
                x = v[t]
                print(f"| {nombre} | {t} | {x['consultas']} | {x['chunks_no_autorizados']} | {x['consultas_con_fuga']} | "
                      f"{x['documento_prohibido']} | {x['resultados_media']} / {x['resultados_min']} |")
    print(f"\nTOTAL LEAK WITH THE FILTER: {resumen['fuga_total']} (must be 0)")
    if resumen["fuga_total"]:
        raise SystemExit("HAY FUGA")


if __name__ == "__main__":
    main()
