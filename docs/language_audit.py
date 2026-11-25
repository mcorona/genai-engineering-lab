#!/usr/bin/env python3
"""Language audit of the repository: classifies every tracked file and measures the Spanish it contains.

Offline and deterministic ($0: no models, no cloud). It reads `git ls-files`, skips `vendor/` and `node_modules/`,
and assigns each file one of five classes (see docs/language-audit.md):

  A  documentation and prose (and the comments and docstrings of code): to be translated into English
  B  intentional Spanish evaluation data (corpora, sources, gold sets, prompts, attack cases): stays in Spanish
  C  recorded evidence (model outputs, runs, generated reports): stays as recorded
  D  operator interface (CLI flags, script names, console messages): gets English aliases
  E  folder names and code identifiers: stay, documented in the glossary
  -  no human-readable text (images without text, certificates, lock files)

Spanish is measured with two word lists: a line counts as Spanish when it has at least two Spanish function
words and more Spanish than English function words. Code spans, URLs, paths and identifiers are removed first.

    python3 docs/language_audit.py                 # summary per class and week
    python3 docs/language_audit.py --json out.json # one record per file
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import subprocess
import sys
import tokenize
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Function words: frequent, short and unambiguous between the two languages.
ES = set("""
el la los las un una unos unas del al que qué y e en por para con sin se su sus es son está están fue ser hay
sí más menos como cómo cuando cuándo donde dónde pero porque si este esta estos estas ese esa esos esas lo le les
ya también cada entre sobre hasta desde muy todo todos toda todas antes después aquí sólo nada otro otra otros
cual cuál quien quién ni sino aunque mientras según tiene tienen puede pueden debe deben hace hacen va van
fueron era eran será sean sea hasta luego así tras ningún ninguna ninguno mismo misma mismos ahora
""".split())
EN = set("""
the of and to in is are was were be been for with on at by from this that these those it its an or not as but
if when which who what each every has have had does do can will would should also than then there their into
per one same any all how why where while because about after before only just over under without our we you
they them his her
""".split())
WORD = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ¿¡]+")
STRIP = [
    re.compile(r"```.*?```", re.S),          # fenced code
    re.compile(r"`[^`\n]*`"),                # inline code
    re.compile(r"https?://\S+"),             # URLs
    re.compile(r"\]\([^)]*\)"),              # link targets
    re.compile(r"<!--.*?-->", re.S),         # HTML comments
    re.compile(r"\S*[_/\\.=]\S*"),           # identifiers, paths, file names, key=value
    re.compile(r"\S*\w-\w\S*"),               # hyphenated ids (a03-es, r02-en) and compounds
]


def clean(text: str) -> str:
    for rx in STRIP:
        text = rx.sub(" ", text)
    return text


def line_lang(line: str) -> str:
    """'es', 'en' or '' (too short or undecided).

    Language codes (ES, EN) and other all-caps tokens are ignored. A short table cell with no English function word
    counts as Spanish when it has two Spanish words (function words, accented words or Spanish name words).
    """
    words = [w.lower() for w in WORD.findall(line) if not (w.isupper() and len(w) > 1)]
    accented = sum(1 for w in words if re.search(r"[áéíóúñ¿¡]", w) and w not in ES)
    es = sum(w in ES for w in words) + accented
    en = sum(w in EN for w in words)
    if es >= 2 and es > en:
        return "es"
    if en >= 2 and en >= es:
        return "en"
    if en == 0 and len(words) <= 8 and es + sum(w in NAME_ES for w in words if w not in ES) >= 2 \
            and (es or accented):
        return "es"
    return ""


def prose_stats(text: str) -> dict:
    """Lines of Spanish and English prose in a text, after removing code and identifiers."""
    es = en = 0
    examples = []
    for raw in clean(text).splitlines():
        for part in re.split(r"\|", raw):          # table cells are judged one by one
            lang = line_lang(part)
            if lang == "es":
                es += 1
                if len(examples) < 2:
                    examples.append(part.strip()[:100])
            elif lang == "en":
                en += 1
    return {"es": es, "en": en, "examples": examples}


# --- Spanish identifiers ------------------------------------------------------------------------------------------
# Spanish words used in folder, file and code names in this repo (reviewed by hand from the name inventory).
NAME_ES = set("""
accion acta actividad actual adaptador adaptadores adoptado afinar agente agentes alcance almacen amenazas analisis
analista andenes antes aprobacion aprobaciones aprobadores arnes arquitectura arrancar asincrono asistente ataques
atribucion auditar auditoria avanzado bitacora bloqueos borrar cadenas caducidad calibracion calibrada calidad
canarios capa capacitacion capturas cargar casos catalogo cero cierre ciclico clasificacion cliente clientes
cobertura comentarios comparacion comparar compartido completa completo compra compradores compras computo comun
con conceptos concurrencia conexion consola construccion construir consulta consultas contenedor contexto contextos
contrasenas contrato contratos copiloto corregida corregir correo correr corrida corridas costo costos cotizacion
creado crear credenciales criterios criticos crudo cuenta dato datos definicion degradacion delegacion descartada
describir descuentos desde desplegado desplegar despliegue destilacion destruir detalle determinista devoluciones
diagrama diccionario directo director diseno dispara disparada distribucion documentos ejecuciones ejemplo embalaje
empaquetado empaquetar ensayo entorno entregable entrenamiento entropia envenenado envenenados envenenamiento
equivalencia escanear escaneo escaneos escribir escritor escritura esquema esquemas estadistica estimacion estres
etiquetado etiquetas evadir evaluacion evaluadores evaluar eventos excepciones experimentos exportador exportar
extraccion extracciones extremo falsos fidelidad fijo fijos finales flete flota flujo formatos fuentes garantias
generacion generar glosario grafica grafo grupos guardia guion guionado herramientas hibrida hola identidad
identidades imagenes indicadores informe ingesta instalacion instalaciones instalar instrumentacion integrado
intencion interna inventario inyeccion inyecciones inyectadas jalar jueces juez laboratorio latencia lectura leer
legado limpiar limpio linea llamadas logistica maquina marco matriz medir mensual mermas metricas minimo modelo
modelos muestreo multiagente multisalto multisemilla navegador negocio nivel nombres normalizacion norte nota notas
nube nucleo nuevo obedece obediente observabilidad occidente oferta operacion orden ordenes orquestar pantalla
paquete para pares pasajes pasarela patrones pedido perdidas perfilador perfiles permisos peticion pide piloto
pizarra plano politica politicas por positivos practica precio precios preguntar preparacion preparar presupuestado
presupuesto presupuestos previos primera primitivas propio proponer proveedores prueba puente puntuar razonamiento
recepcion rechazados reclamaciones recuperacion redaccion reescritura reevaluado referencias reglas reintento
relaciones remision remoto reorden reparto repeticion repeticiones reporta reporte reproduccion requisitos reservada
respaldos responde respuesta respuestas resultado resultados resumen resumir retencion revisar revision revisor
riesgos rotacion roto rubricas ruteo salida salidas secretos seguimiento seguridad seguro sellar sellos semana
semantico sensibilidad servicio servidor simulado sin sincrono sistema solape solicitudes solo sonda subagente
subagentes sumidero supresiones tabla tablas tablero tareas tarifas temperaturas texto tiempos transferencias
transporte trayectorias trazas turnos ultima umbral una usuarios uso vaciar validacion validado validar
variabilidad verdad verificacion verificar versionados versiones viaticos viva vivo
""".split())


# Command-line flags that are already English. Every other flag in the repository is Spanish.
EN_FLAGS = set("""
admin api-key-env api-url backend base-url cdk-out checkov chrome ci config cost-explorer diff dir dry-run frameworks
github gitleaks json jwks k lang langfuse local local-url loop max-tokens oauth otlp pool prompt python-cdk rag region
sdk seed set suite synth tokens var version workers workflow zip help h
""".split())


def spanish_flag(flag: str) -> bool:
    return flag.lstrip("-") not in EN_FLAGS


def spanish_name(name: str) -> bool:
    parts = re.split(r"[_\-.\s/]+|(?<=[a-z])(?=[A-Z])", name)
    return any(p.lower() in NAME_ES for p in parts if p)


# --- Per file-type extraction ---------------------------------------------------------------------------------------
FLAG = re.compile(r"""add_argument\(\s*["'](-{1,2}[\w-]+)["']""")
SH_FLAG = re.compile(r"""^\s*(?:\|\s*)?["']?(-{1,2}[a-z][\w-]*)["']?\)""", re.M)


MSG_CALLS = {"print", "exit", "error", "warning", "warn", "info", "debug", "fail", "SystemExit", "ArgumentParser",
             "add_argument", "add_parser", "echo", "input", "log", "skip"}


def _call_name(node: ast.Call) -> str:
    f = node.func
    return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")


def _strings(node) -> list:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.append(n.value)
    return out


def python_parts(src: str) -> dict:
    """Comments and docstrings (class A), console messages and CLI help (class D) and identifiers (class E).

    Other string literals (prompts, SQL, test data, expected outputs) are not counted: they are behavior.
    """
    comments, docstrings, messages, idents = [], [], [], set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {"prose": src, "messages": "", "idents": set(), "flags": [], "cli": False}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.append(body[0].value.value)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            idents.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            idents.add(node.id)
        elif isinstance(node, ast.arg):
            idents.add(node.arg)
        elif isinstance(node, ast.Call) and _call_name(node) in MSG_CALLS:
            messages.extend(_strings(node))
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                comments.append(tok.string.lstrip("#"))
    except (tokenize.TokenError, IndentationError):
        pass
    cli = bool(re.search(r"argparse|sys\.argv|__name__\s*==\s*[\"']__main__", src))
    return {"prose": "\n".join(comments + docstrings), "messages": "\n".join(messages),
            "idents": {i for i in idents if spanish_name(i)}, "flags": FLAG.findall(src), "cli": cli}


def hash_comments(src: str, marks=("#",)) -> str:
    out = []
    for line in src.splitlines():
        s = line.strip()
        for m in marks:
            if s.startswith(m):
                out.append(s[len(m):])
                break
            if f" {m} " in line and m == "#":
                out.append(line.split(f" {m} ", 1)[1])
                break
    return "\n".join(out)


def json_strings(obj, keys: set, values: list):
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            json_strings(v, keys, values)
    elif isinstance(obj, list):
        for v in obj:
            json_strings(v, keys, values)
    elif isinstance(obj, str):
        values.append(obj)


def data_parts(path: str, text: str) -> dict:
    keys: set = set()
    values: list = []
    if path.endswith(".jsonl"):
        for line in text.splitlines():
            try:
                json_strings(json.loads(line), keys, values)
            except ValueError:
                values.append(line)
    elif path.endswith(".json"):
        try:
            json_strings(json.loads(text), keys, values)
        except ValueError:
            values.append(text)
    elif path.endswith(".csv"):
        lines = text.splitlines()
        if lines:
            keys = set(lines[0].split(","))
        values = lines[1:]
    else:
        values = [text]
    return {"prose": "\n".join(values), "keys": {k for k in keys if spanish_name(k)}}


# --- Classification ------------------------------------------------------------------------------------------------
NO_TEXT_EXT = {".png", ".jpg", ".pem", ".gz", ".lock", ".hcl"}
NO_TEXT_NAMES = {".python-version", "icon.png", "uv.lock"}
CODE_EXT = {".py", ".sh", ".sql", ".tf", ".cedar", ".yml", ".yaml", ".toml", ".ipynb", ""}
DATA_EXT = {".json", ".jsonl", ".csv", ".txt"}

# Folders whose contents are intentional Spanish (or bilingual) evaluation data: class B.
B_DIRS = re.compile(r"/(corpus|corpus_beta|fuentes|golden|datasets|prompts|rubricas|legado|verdad|escaneos|pdf|"
                    r"pdf_inyeccion|imagenes|imagenes_inyeccion|ataques|kb_envenenados|data|loader|mocks)/")
B_FILES = {
    "semana-02/texto_es.txt", "semana-02/texto_en.txt", "semana-01/names.txt", "semana-04/consultas.jsonl",
    "semana-13/seguridad/artnot.sql", "semana-16/seguridad/inyecciones.sql", "semana-16/seguridad/limpiar_inyecciones.sql",
    "semana-16/eval/conceptos.json", "semana-16/navegador/verdad_pantalla.json", "semana-13/herramientas/diccionario_extra.json",
    "semana-18/pizarra/sellos.json", "semana-17/trayectorias/manifiesto.json", "semana-17/trayectorias/referencias.jsonl",
    "semana-14/auth/roles_bd.sql", "semana-07/schema.sql", "semana-07/schema_completo.sql",
    "semana-03/reglas_legado.md",  # read into the system prompt by evaluar_sql.py and rag_reglas.py
}
# Recorded evidence outside a results folder: class C.
C_DIRS = re.compile(r"/(resultados|resultados-n5|corridas|baseline|snapshots|paquete|ejemplo|entrenamiento/data|"
                    r"destilacion|dpo)/")
C_FILES = re.compile(r"^semana-0[12]/[^/]+\.(csv|png)$|^semana-01/perdidas")
EVAL_CASES = re.compile(r"legacy-schema-audit/evals/")
# Prompts that a model reads (Claude Code skills and subagents): editing them changes measured behavior, so they are B.
PROMPT_FILES = re.compile(r"/(skills/[^/]+/SKILL\.md|agents/[^/]+\.md)$")
# Docstrings that a framework sends to the model as tool descriptions: behavior, not documentation.
BEHAVIOR_DOCSTRINGS = {"semana-17/comparacion/agente_langgraph.py": "LangChain @tool docstrings are tool descriptions"}


def week_of(path: str) -> str:
    m = re.match(r"semana-(\d+)/", path)
    return m.group(1) if m else "root"


def generated_md(path: str, scripts: dict) -> list:
    """Scripts that name this results file (a sign that the file is generated, not written by hand)."""
    base, week = Path(path).name, path.split("/")[0] + "/"
    return sorted(s for s, src in scripts.items()
                  if s.startswith(week) and base in src and "/tests/" not in s and not Path(s).name.startswith("test_"))


def classify(path: str, text: str | None, scripts: dict) -> dict:
    p = "/" + path
    ext = Path(path).suffix
    name = Path(path).name
    rec = {"path": path, "week": week_of(path), "es_lines": 0, "en_lines": 0, "es_messages": 0,
           "es_idents": [], "es_keys": [], "flags": [], "generated_by": [], "examples": []}
    if text is None or ext in NO_TEXT_EXT or name in NO_TEXT_NAMES:
        rec["cls"] = "B" if B_DIRS.search(p) else ("C" if (C_DIRS.search(p) or C_FILES.search(path)) else "-")
        if name in ("icon.png",) or ext in (".pem", ".lock", ".hcl") or name in NO_TEXT_NAMES:
            rec["cls"] = "-"
        if ext == ".pdf":
            rec["cls"] = "B" if B_DIRS.search(p) else "C"
        return rec

    if ext == ".py":
        parts = python_parts(text)
        prose = parts["prose"]
        rec["es_idents"] = sorted(parts["idents"])
        rec["flags"] = parts["flags"]
        msg = prose_stats(parts["messages"])
        rec["es_messages"] = msg["es"]
    elif ext == ".ipynb":
        try:
            nb = json.loads(text)
            prose = "\n".join("".join(c.get("source", [])) for c in nb.get("cells", []) if c.get("cell_type") == "markdown")
        except ValueError:
            prose = text
    elif ext == ".sh":
        prose = hash_comments(text)
        echoes = "\n".join(re.findall(r"""(?:echo|printf|die|log)\s+["']([^"'\n]+)""", text))
        rec["es_messages"] = prose_stats(echoes)["es"]
        rec["flags"] = SH_FLAG.findall(text)
    elif ext in (".yml", ".yaml", ".toml", ".tf", ".hcl") or name in ("Dockerfile", ".gitignore"):
        prose = hash_comments(text)
        if ext in (".yml", ".yaml"):
            prose += "\n" + "\n".join(re.findall(r"(?:description|name):\s*\"?([^\"\n]+)", text))
    elif ext == ".sql":
        prose = hash_comments(text, ("--",)) + "\n" + "\n".join(re.findall(r"COMMENT ON .*? IS '([^']*)'", text, re.S))
    elif ext == ".cedar":
        prose = hash_comments(text, ("//",))
    elif ext == ".mmd":
        prose = "\n".join(re.findall(r"[\[\(\{\"|]([^\]\)\}\"|]{3,})", text)) + "\n" + hash_comments(text, ("%%",))
    elif ext == ".svg":
        prose = " ".join(re.findall(r">([^<>]{2,})<", text))
    elif ext in DATA_EXT:
        parts = data_parts(path, text)
        prose = parts["prose"]
        rec["es_keys"] = sorted(parts["keys"])
    else:  # .md, .html, LICENSE and the rest: prose
        prose = re.sub(r"<[^>]+>", " ", text) if ext == ".html" else text

    st = prose_stats(prose)
    rec["es_lines"], rec["en_lines"], rec["examples"] = st["es"], st["en"], st["examples"]

    # Class by role, not by language: a Spanish gold set is B even if it is short, an English README is still A.
    # Python and shell are code wherever they live: D when they are a command an operator runs, A otherwise.
    if ext in (".py", ".sh"):
        is_test = "/tests/" in p or name.startswith(("test_", "conftest"))
        cli = True if ext == ".sh" else parts["cli"]
        cls = "D" if cli and not is_test else "A"
    elif B_DIRS.search(p) or path in B_FILES or EVAL_CASES.search(path) or PROMPT_FILES.search(p):
        cls = "B"
    elif C_DIRS.search(p) or C_FILES.search(path):
        cls = "C"
        if ext == ".md" and re.search(r"/resultados/[^/]+\.md$", path):
            gen = generated_md(path, scripts)
            rec["generated_by"] = gen
            cls = "A"  # explanatory results documents are A, even when a script writes them (see generated_by)
    elif ext in DATA_EXT and path.startswith("semana-"):
        cls = "E" if rec["es_keys"] else "A"   # configuration: its Spanish keys are identifiers
    else:
        cls = "A"
    rec["cls"] = cls
    return rec


def tracked() -> list:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if not re.search(r"(^|/)(vendor|node_modules)/", p)]


def audit() -> list:
    files = tracked()
    texts = {}
    for f in files:
        try:
            texts[f] = (ROOT / f).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            texts[f] = None
    scripts = {f: t for f, t in texts.items() if t and f.endswith((".py", ".sh", ".yml"))}
    recs = [classify(f, texts[f], scripts) for f in files]
    # Frozen files: their SHA-256 is stored in another tracked file (a manifest or a test). Any byte change, even a
    # translated comment, breaks the freeze, so they are exceptions to the translation.
    digest = {hashlib.sha256((ROOT / f).read_bytes()).hexdigest(): f for f in files if (ROOT / f).is_file()}
    frozen = defaultdict(set)
    for f, t in texts.items():
        if t and f != "uv.lock":
            for h in re.findall(r"\b[0-9a-f]{64}\b", t):
                if h in digest and digest[h] != f:
                    frozen[digest[h]].add(f)
    for r in recs:
        r["frozen_by"] = sorted(frozen.get(r["path"], ()))
        r["behavior_docstrings"] = BEHAVIOR_DOCSTRINGS.get(r["path"], "")
        r["spanish_name"] = spanish_name(Path(r["path"]).stem)
    return recs


CLASS_NAMES = {"A": "documentation and prose", "B": "Spanish evaluation data", "C": "recorded evidence",
               "D": "operator interface", "E": "names and identifiers", "-": "no human-readable text"}
BEGIN, END = "<!-- BEGIN GENERATED INVENTORY -->", "<!-- END GENERATED INVENTORY -->"


def weeks_of(recs) -> list:
    return sorted({r["week"] for r in recs}, key=lambda w: (w != "root", w))


def marks(r) -> str:
    out = []
    if r["es_lines"]:
        out.append(f"es prose: {r['es_lines']}")
    if r["es_messages"]:
        out.append(f"es messages: {r['es_messages']}")
    es_flags = [f for f in r["flags"] if spanish_flag(f)]
    if es_flags:
        out.append("es flags: " + " ".join(f"`{f}`" for f in sorted(set(es_flags))))
    if r["es_keys"]:
        out.append(f"es keys: {len(r['es_keys'])}")
    if r["frozen_by"]:
        out.append("frozen by " + ", ".join(f"`{f}`" for f in r["frozen_by"][:2]))
    if r["generated_by"]:
        out.append("named in " + ", ".join(f"`{f}`" for f in r["generated_by"][:2]))
    if r["behavior_docstrings"]:
        out.append(r["behavior_docstrings"])
    return "; ".join(out)


def render(recs) -> str:
    weeks = weeks_of(recs)
    by = defaultdict(Counter)
    es = defaultdict(Counter)
    for r in recs:
        by[r["cls"]][r["week"]] += 1
        if r["es_lines"] or r["es_messages"] or r["es_keys"]:
            es[r["cls"]][r["week"]] += 1
    lines = [BEGIN, "", "Generated by `python3 docs/language_audit.py --markdown docs/language-audit.md`. "
             "Do not edit by hand. Every file, one per row: [language-audit-files.tsv](language-audit-files.tsv).", ""]
    lines.append("### Files per class and week")
    lines.append("")
    lines.append("| Class | " + " | ".join("root" if w == "root" else w for w in weeks) + " | Total |")
    lines.append("|---" * (len(weeks) + 2) + "|")
    for c in "ABCDE-":
        lines.append(f"| {c} | " + " | ".join(str(by[c][w]) for w in weeks) + f" | **{sum(by[c].values())}** |")
    lines.append(f"| All | " + " | ".join(str(sum(by[c][w] for c in by)) for w in weeks) + f" | **{len(recs)}** |")
    lines += ["", "### Files with Spanish text, per class and week", "",
              "Spanish prose lines, Spanish console messages or Spanish JSON/CSV keys. For B and C this is expected.", ""]
    lines.append("| Class | " + " | ".join("root" if w == "root" else w for w in weeks) + " | Total |")
    lines.append("|---" * (len(weeks) + 2) + "|")
    for c in "ABCDE":
        lines.append(f"| {c} | " + " | ".join(str(es[c][w]) for w in weeks) + f" | **{sum(es[c].values())}** |")
    todo = [r for r in recs if r["cls"] in "AD" and r["es_lines"]]
    lines += ["", "### Class A and D files with Spanish prose (comments, docstrings, documentation)", "",
              "| File | Class | Spanish lines | English lines | Note | First Spanish line |", "|---|---|---|---|---|---|"]
    for r in sorted(todo, key=lambda r: (-r["es_lines"], r["path"])):
        ex = (r["examples"][0] if r["examples"] else "").replace("|", "/").replace("`", "")
        note = "frozen: stays" if r["frozen_by"] else (r["behavior_docstrings"] or "")
        lines.append(f"| `{r['path']}` | {r['cls']} | {r['es_lines']} | {r['en_lines']} | {note} | {ex} |")
    msgs = [r for r in recs if r["es_messages"]]
    lines += ["", "### Files with Spanish console messages", "",
              "| File | Class | Spanish messages |", "|---|---|---|"]
    for r in sorted(msgs, key=lambda r: (-r["es_messages"], r["path"])):
        lines.append(f"| `{r['path']}` | {r['cls']} | {r['es_messages']} |")
    lines += ["", "### File list per week", "",
              "Folders with more than 12 files of one class are collapsed to one line; the TSV lists each file.", ""]
    for w in weeks:
        mine = [r for r in recs if r["week"] == w]
        title = "Repository root" if w == "root" else f"Week {int(w)} (`semana-{w}/`)"
        counts = ", ".join(f"{c}: {sum(1 for r in mine if r['cls'] == c)}" for c in "ABCDE-"
                           if any(r["cls"] == c for r in mine))
        lines += [f"<details><summary><b>{title}</b>: {len(mine)} files ({counts})</summary>", ""]
        for c in "ABCDE-":
            rs = [r for r in mine if r["cls"] == c]
            if not rs:
                continue
            lines += [f"**{c}: {CLASS_NAMES[c]}** ({len(rs)})", ""]
            folders = defaultdict(list)
            for r in rs:
                folders[str(Path(r["path"]).parent)].append(r)
            for folder in sorted(folders):
                group = folders[folder]
                if len(group) > 12:
                    n_es = sum(1 for r in group if r["es_lines"] or r["es_messages"] or r["es_keys"])
                    lines.append(f"- `{folder}/` ({len(group)} files; {n_es} with Spanish text)")
                else:
                    for r in sorted(group, key=lambda r: r["path"]):
                        m = marks(r)
                        lines.append(f"- `{r['path']}`" + (f": {m}" if m else ""))
            lines.append("")
        lines += ["</details>", ""]
    lines.append(END)
    return "\n".join(lines)


def tsv(recs) -> str:
    head = "path\tweek\tclass\tes_prose_lines\ten_prose_lines\tes_messages\tes_flags\tes_keys\tes_identifiers\tfrozen_by\tnamed_in"
    rows = [head]
    for r in recs:
        es_flags = " ".join(sorted({f for f in r["flags"] if spanish_flag(f)}))
        rows.append("\t".join([r["path"], r["week"], r["cls"], str(r["es_lines"]), str(r["en_lines"]),
                               str(r["es_messages"]), es_flags, str(len(r["es_keys"])), str(len(r["es_idents"])),
                               " ".join(r["frozen_by"]), " ".join(r["generated_by"])]))
    return "\n".join(rows) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", help="write one record per file to this path")
    ap.add_argument("--markdown", help="replace the generated inventory in this Markdown file, and write the TSV next to it")
    ap.add_argument("--check", help="exit 1 if the generated inventory in this Markdown file is out of date")
    args = ap.parse_args()
    recs = audit()
    if args.json:
        Path(args.json).write_text(json.dumps(recs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for target in filter(None, (args.markdown, args.check)):
        doc = Path(target)
        text = doc.read_text(encoding="utf-8")
        new = text[:text.index(BEGIN)] + render(recs) + text[text.index(END) + len(END):]
        tsv_path = doc.with_name("language-audit-files.tsv")
        if args.check:
            stale = new != text or not tsv_path.exists() or tsv_path.read_text(encoding="utf-8") != tsv(recs)
            if stale:
                print(f"{target} is out of date: run python3 docs/language_audit.py --markdown {target}")
                return 1
        else:
            doc.write_text(new, encoding="utf-8")
            tsv_path.write_text(tsv(recs), encoding="utf-8")
    by = defaultdict(Counter)
    for r in recs:
        by[r["cls"]][r["week"]] += 1
    weeks = weeks_of(recs)
    print("class " + " ".join(f"{w:>4}" for w in weeks) + "  total")
    for c in "ABCDE-":
        print(f"{c:5} " + " ".join(f"{by[c][w]:>4}" for w in weeks) + f"  {sum(by[c].values()):>5}")
    print(f"files: {len(recs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
