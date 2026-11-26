"""Everything an English-speaking reader reads is in English. Offline, $0, standard library only.

What is checked (the classes are the ones of docs/language-audit.md, assigned by docs/language_audit.py):

- prose files: every class A file that is not code (Markdown, workflows, Terraform, configuration comments…), every
  README and every Markdown file under docs/, whatever its class, has no Spanish prose line;
- code: the comments and docstrings of every Python and shell file (classes A and D) have no Spanish line;
- console messages and help text (`print`, `exit`, `argparse` help, `echo`…) of every Python and shell file are
  English.

Classes B (Spanish evaluation data), C (recorded evidence) and E (names) are out of scope by definition.

A line is Spanish prose when docs/language_audit.py's detector says so after this test removes what is not prose:
code spans, quoted strings inside an English sentence, *italic* mentions, URLs, identifiers and file names. On top of
the audit's rule, a Spanish line needs at least one Spanish function word, so a list of glossary terms
(`devolución, reclamación`) is not prose. The generated inventory of docs/language-audit.md (between its
`GENERATED INVENTORY` markers) quotes the Spanish the audit found and is skipped.

Every line that stays in Spanish on purpose is listed, with its reason, in the section "What stays in Spanish on
purpose" of docs/language-audit.md. The test reads its exceptions from that table, so the document is the single
source of truth, and it fails when a row no longer matches anything (a stale exception).
"""
from __future__ import annotations

import ast
import fnmatch
import functools
import io
import json
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT_DOC = ROOT / "docs" / "language-audit.md"
SECTION = "## What stays in Spanish on purpose"
sys.path.insert(0, str(ROOT / "docs"))
import language_audit as la  # noqa: E402  (standard library only)

KINDS = {"prose", "comments", "messages", "any"}

# Spanish lines that are not deliberate but are not translated yet, because editing their file starts a paid
# evaluation workflow (the one named in the comment). They are translated in the next code change of that week, which
# pays for that run anyway; the stale check below fails once a line is fixed, so this list cannot outlive its lines.
# (path, kind, text in the line)
PENDING: list[tuple[str, str, str]] = [
    ("semana-07/ci/generar_datos.py", "comments", "Copia de inventory-copilot"),            # nlq-semana-07, eval-16, eval-17
    ("semana-13/tests/test_herramientas.py", "messages", "no se revelan los nombres"),       # eval-semana-13
    ("semana-13/tests/test_herramientas.py", "messages", "el modelo no debe poder elegir"),  # eval-semana-13
    ("semana-14/tests/test_linea_base.py", "messages", "sin prueba referenciada"),           # eval-semana-14
    ("semana-15/agentcore/requisitos_runtime.txt", "prose", "Dependencias del paquete"),     # eval-semana-15
    ("semana-15/tests/test_equivalencia.py", "messages", "sin los entornos de"),             # eval-semana-15
    ("semana-15/tests/test_eval.py", "messages", "sin los entornos de"),                     # eval-semana-15
    ("semana-15/tests/test_multiagente.py", "messages", "sin los entornos de"),              # eval-semana-15
    ("semana-15/tests/test_spikes.py", "messages", "sin los entornos de"),                   # eval-semana-15
    ("semana-16/corrida/correr.py", "messages", "no debe poder escribir"),                   # eval-semana-16
    ("semana-16/tests/test_eval_plugin.py", "messages", "sin grader de resultado"),          # eval-semana-16
    ("semana-16/tests/test_hooks_auditoria.py", "messages", "sin PG_DSN ni PG_ADMIN_DSN"),   # eval-semana-16
    ("semana-16/tests/test_verdad.py", "messages", "cambió sin regenerar"),                  # eval-semana-16
    ("semana-16/tests/test_verdad.py", "messages", "difiere de la congelada"),               # eval-semana-16
]


# --- The detector ----------------------------------------------------------------------------------------------------
# Frequent Spanish words that are not English words, for short messages ("Keycloak no está corriendo") that have fewer
# than two function words. They only add weight: a line still needs a Spanish function word to count.
EXTRA_ES = set("""
debe deben debería tiene tienen tenía hay había puede pueden pudo existe existen falta faltan falló fallida fallido
fallaron corre corren corriendo correr usa usar usando requiere requieren necesita sale salen revisa revise valida
no ausente todavía aún nunca siempre ninguno vacío vacía vacíos vacías listo lista hecho nuevo nueva nuevos nuevas mismo
encontró encontrado encontrada encontrados borrado borrada creado creada toca tocar llamar llama llamada respuesta
pregunta preguntas archivo archivos cambia cambiar cambio dentro fuera arriba abajo bien mal primero primera último
última dos tres cuatro cinco seis siete ocho nueve diez cuánto cuántos cuántas cuál quién qué dónde cómo cuándo
""".split())
# Repository words (docs/language_audit.py NAME_ES) that are also English words.
EN_HOMOGRAPHS = {"director", "piloto", "nota", "plano", "hola", "una"}
# Spanish function words missing from the audit's list because they are also English fragments (`de facto`).
EXTRA_FUNCTION = {"de", "lo", "nos", "o", "u"}
# Spanish endings (gerund, adverb, participle, -ción plural). They only add weight, like EXTRA_ES.
SPANISH_SUFFIX = re.compile(r"(ciones|siones|iendo|mente|\w{3}(?:ado|ada|ido|ida)s?)$")
ACCENTED = re.compile(r"[áéíóúñ¿¡]")
FLAG_TOKEN = re.compile(r"(?<![\w-])--?[A-Za-z][\w-]*")
QUOTED = re.compile(r"\"[^\"\n]{2,}\"|“[^”\n]{2,}”|«[^»\n]{2,}»")
ITALIC = re.compile(r"(?<![\w*])\*(?!\s)[^*\n]{1,60}(?<!\s)\*(?![\w*])|(?<![\w_])_(?!\s)[^_\n]{1,60}(?<!\s)_(?![\w_])")
WORD_LIST = re.compile(r"^\s*[\wÁÉÍÓÚÜÑáéíóúüñ]+(\s*[,/]\s*[\wÁÉÍÓÚÜÑáéíóúüñ]+)*\s*[:.]?\s*$")
# A command line in a usage docstring or a comment: its arguments are names and recorded values, not prose. Only the
# comment after ` # ` is read.
COMMAND = re.compile(r"^\s*(?:\$\s*)?(?:[A-Z][A-Z0-9_]*=\S*\s+)*(?:(?:python3?|uv|\.venv/\S+|bash|aws|gh|git|cdk|terraform|"
                     r"docker|pytest|make)(?:\s|$)|\S+\.(?:py|sh)\s+(?:-|\[-|$)|\S+\.(?:py|sh)$)")


def _weights(text: str) -> tuple[int, int, int, int, int]:
    """Spanish function words, Spanish words of any kind, accented words, English function words, all words."""
    words = [w.lower() for w in la.WORD.findall(text) if not (w.isupper() and len(w) > 1)]
    if "es" in words and "en" in words:      # language codes: `es or en`, `--idiomas es en`
        words = [w for w in words if w not in ("es", "en")]
    function = sum((w in la.ES or w in EXTRA_FUNCTION) and w not in ("y", "e") for w in words)
    spanish = sum(w in la.ES or w in EXTRA_FUNCTION or w in EXTRA_ES or (w in la.NAME_ES and w not in EN_HOMOGRAPHS)
                  or bool(ACCENTED.search(w)) or bool(SPANISH_SUFFIX.search(w)) for w in words)
    accented = sum(bool(ACCENTED.search(w)) for w in words)
    return function, spanish, accented, sum(w in la.EN for w in words), len(words)


def _spanish_text(text: str, cell: bool) -> bool:
    """Spanish prose: a Spanish function word, two Spanish words, and more Spanish than English. A short fragment with
    no English word (`presupuesto (simulación)`) also counts when it has an accent. In a table, a cell of up to three
    words is a term (the glossary's Spanish column), not prose."""
    if WORD_LIST.match(text):                # a list of terms (`devolución, reclamación`) is not a sentence
        return False
    function, spanish, accented, english, total = _weights(text)
    if cell and total <= 3:                  # a term in a table (`punto de reorden` | reorder point), not a sentence
        return False
    if function >= 1 and spanish >= 2 and spanish > english:
        return True
    return not cell and english == 0 and accented >= 1 and spanish >= 2 and total <= 8


def _without_quotes(cell: str) -> list[str]:
    """The cell without its quotations. A quote that opens or closes on another line is cut both ways."""
    out = QUOTED.sub(" ", cell)
    if out.count('"') % 2:
        return [out.rsplit('"', 1)[0], out.split('"', 1)[1]]
    return [out]


def is_spanish(line: str) -> bool:
    """True when a line (or one table cell of it) is Spanish prose.

    A quotation in double quotes (of a gold set, a recorded answer, a message) is not prose: the text around it decides.
    """
    cells = prepare(line).split("|")
    return any(all(_spanish_text(v, len(cells) > 1) for v in _without_quotes(cell)) for cell in cells)


def prepare(line: str) -> str:
    """The prose of a line: without code, URLs, identifiers, flags, italic mentions, or a command line's arguments."""
    if COMMAND.match(line):
        line = line.split(" # ", 1)[1] if " # " in line else ""
    return ITALIC.sub(" ", la.clean(FLAG_TOKEN.sub(" ", line)))


# --- Extraction: (line number, text, kind) per file -----------------------------------------------------------------
def markdown_lines(text: str):
    fence = None
    in_comment = generated = False
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if "<!-- BEGIN GENERATED" in s:
            generated = True
        if "<!-- END GENERATED" in s:
            generated = False
            continue
        if generated:
            continue
        if fence:
            if s.startswith(fence):
                fence = None
            continue
        m = re.match(r"(`{3,}|~{3,})", s)
        if m:
            fence = m.group(1)
            continue
        if in_comment:
            if "-->" not in line:
                continue
            in_comment, line = False, line.split("-->", 1)[1]
        if "<!--" in line and "-->" not in line.split("<!--", 1)[1]:
            in_comment, line = True, line.split("<!--", 1)[0]
        yield n, re.sub(r"<[^>]+>", " ", line), "prose"


def hash_comment_lines(text: str, marks=("#",), kind="comments"):
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s.startswith("#!"):
            continue
        for m in marks:
            if s.startswith(m):
                yield n, s[len(m):], kind
                break
            if m == "#" and " # " in line:
                yield n, line.split(" # ", 1)[1], kind
                break


ECHO = re.compile(r"""(?:echo|printf|die|log|warn|fail)\s+(?:-[a-z]+\s+)*(["'])(.+?)\1""")


def shell_lines(text: str):
    yield from hash_comment_lines(text)
    for n, line in enumerate(text.splitlines(), 1):
        for m in ECHO.finditer(line):
            yield n, m.group(2), "messages"


def _string_values(node):
    """The strings under a node; an f-string is one string, with a space for each placeholder."""
    inside = set()
    for c in ast.walk(node):
        if isinstance(c, ast.JoinedStr):
            parts = []
            for v in c.values:
                inside.add(id(v))
                parts.append(v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else " ")
            yield c.lineno, "".join(parts)
    for c in ast.walk(node):
        if isinstance(c, ast.Constant) and isinstance(c.value, str) and id(c) not in inside:
            yield c.lineno, c.value


def python_lines(src: str):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT and not tok.string.startswith("#!"):
                yield tok.start[0], tok.string.lstrip("#"), "comments"
    except (tokenize.TokenError, IndentationError):
        pass
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                for k, line in enumerate(body[0].value.value.splitlines()):
                    yield body[0].value.lineno + k, line, "comments"
        message = None
        if isinstance(node, ast.Call) and la._call_name(node) in MESSAGE_CALLS:
            message = node
        elif isinstance(node, ast.Raise) and node.exc is not None:
            message = node.exc                      # an exception's message reaches the operator's console
        elif isinstance(node, ast.Assert) and node.msg is not None:
            message = node.msg                      # pytest prints it when the assertion fails
        elif isinstance(node, ast.keyword) and node.arg == "reason":
            message = node.value                    # skip and xfail reasons are printed by pytest -rs
        if message is not None:
            for lineno, value in _string_values(message):
                for k, line in enumerate(value.splitlines()):
                    yield lineno + k, line, "messages"


MESSAGE_CALLS = la.MSG_CALLS | {"skipif", "xfail", "critical", "exception"}
JSON_VALUE = re.compile(r'"((?:[^"\\\n]|\\.)*)"(?!\s*:)')


def json_lines(text: str):
    for n, line in enumerate(text.splitlines(), 1):
        for m in JSON_VALUE.finditer(line):
            try:
                yield n, json.loads(f'"{m.group(1)}"'), "prose"
            except ValueError:
                yield n, m.group(1), "prose"


def notebook_lines(text: str):
    try:
        cells = json.loads(text).get("cells", [])
    except ValueError:
        return
    raw = text.splitlines()
    for cell in cells:
        if cell.get("cell_type") != "markdown":
            continue
        for n, line, kind in markdown_lines("".join(cell.get("source", []))):
            probe = json.dumps(line)[1:-1][:40]
            where = next((i for i, r in enumerate(raw, 1) if probe and probe in r), 0)
            yield where, line, kind


def lines_of(path: str, text: str):
    """The readable lines of a file, by kind: prose (documentation), comments (and docstrings) and messages."""
    ext, name = Path(path).suffix, Path(path).name
    if ext == ".py":
        yield from python_lines(text)
    elif ext == ".sh":
        yield from shell_lines(text)
    elif ext == ".ipynb":
        yield from notebook_lines(text)
    elif ext in (".yml", ".yaml"):
        yield from hash_comment_lines(text, kind="prose")
        for n, line in enumerate(text.splitlines(), 1):
            m = re.match(r"\s*-?\s*(?:name|description):\s*[\"']?([^\"'\n]+)", line)
            if m:
                yield n, m.group(1), "prose"
            for e in ECHO.finditer(line):
                yield n, e.group(2), "messages"
    elif ext in (".toml", ".tf", ".hcl", ".txt") or name in ("Dockerfile", ".gitignore"):
        yield from hash_comment_lines(text, kind="prose")
    elif ext == ".sql":
        yield from hash_comment_lines(text, ("--",), kind="prose")
    elif ext == ".cedar":
        yield from hash_comment_lines(text, ("//",), kind="prose")
    elif ext == ".mmd":
        yield from hash_comment_lines(text, ("%%",), kind="prose")
        for n, line in enumerate(text.splitlines(), 1):
            for part in re.findall(r"[\[\(\{\"|]([^\]\)\}\"|]{3,})", line):
                yield n, part, "prose"
    elif ext == ".svg":
        for n, line in enumerate(text.splitlines(), 1):
            for part in re.findall(r">([^<>]{2,})<", line):
                yield n, part, "prose"
    elif ext in (".json", ".jsonl"):
        yield from json_lines(text)
    else:  # Markdown, HTML, TSV, LICENSE…
        yield from markdown_lines(text)


# --- Scope -------------------------------------------------------------------------------------------------------------
@functools.cache
def records() -> dict:
    return {r["path"]: r for r in la.audit()}


def in_scope(path: str, cls: str) -> bool:
    if Path(path).suffix in (".py", ".sh"):
        return cls in ("A", "D")
    if re.search(r"(^|/)README[^/]*\.md$", path) or re.match(r"docs/[^/]+\.md$", path):
        return True
    return cls == "A"


@functools.cache
def findings() -> tuple:
    """Every Spanish line in scope: (path, line number, kind, text)."""
    out = []
    for path, rec in sorted(records().items()):
        if not in_scope(path, rec["cls"]):
            continue
        try:
            text = (ROOT / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        seen = set()
        for n, line, kind in lines_of(path, text):
            if line.strip() and (n, kind, line) not in seen and is_spanish(line):
                seen.add((n, kind, line))
                out.append((path, n, kind, line.strip()))
    return tuple(out)


# --- Exceptions: the table in docs/language-audit.md -----------------------------------------------------------------
@functools.cache
def exceptions() -> tuple:
    """Rows of the table: (patterns, kind, texts, what, why). `texts` empty = every line of that kind."""
    doc = AUDIT_DOC.read_text(encoding="utf-8")
    assert SECTION in doc, f"docs/language-audit.md has no section {SECTION!r}"
    section = doc.split(SECTION, 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in section.splitlines():
        if not line.startswith("| ") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0] == "Path or pattern":
            continue
        assert len(cells) == 5, f"exception row needs 5 cells (path, kind, text, what, why): {line}"
        patterns = re.findall(r"`([^`]+)`", cells[0])
        kind = cells[1].strip("`")
        texts = [] if cells[2] in ("*", "`*`") else re.findall(r"`([^`]+)`", cells[2])
        rows.append((tuple(patterns), kind, tuple(texts), cells[3], cells[4]))
    return tuple(rows)


def _matches(rule, path: str, kind: str, line: str) -> bool:
    patterns, rkind, texts = rule[:3]
    return (any(fnmatch.fnmatchcase(path, p) for p in patterns) and rkind in ("any", kind)
            and (not texts or any(t in line for t in texts)))


def allowed(path: str, kind: str, line: str) -> bool:
    return any(_matches(r, path, kind, line) for r in exceptions()) or \
        any(_matches(((p,), k, (t,) if t else ()), path, kind, line) for p, k, t in PENDING)


def report(kinds: set) -> list[str]:
    return [f"{p}:{n} [{k}] {t[:140]}" for p, n, k, t in findings() if k in kinds and not allowed(p, k, t)]


# --- Tests -----------------------------------------------------------------------------------------------------------
def test_the_detector_tells_spanish_prose_from_english():
    spanish = ["Lectura del esquema legado básico (almmst, artmst sin costo ni proveedor)",
               "el bucket de logs no se replica entre regiones; prod lo decide el ADR",
               "| IPv4 pública en uso | 0.005 |", "Keycloak no está corriendo"]
    english = ["The week 19 eval reads `semana-19/resultados/eval_aws.json` and writes `costo_por_tarea`.",
               'Case 3 answered "El acceso a legado es de solo lectura" and the judge accepted it.',
               "| devolución, reclamación | return, customer claim |",
               "Spanish function words (*el*, *que*, *para*…) count; the run `--corrida piloto` is recorded.",
               "| `quedan` | `nada` | remaining: none |", "es or en", "--idiomas es en"]
    assert [s for s in spanish if not is_spanish(s)] == []
    assert [s for s in english if is_spanish(s)] == []


def test_the_exceptions_table_is_complete_and_justified():
    rows = exceptions()
    assert len(rows) >= 9
    tracked = list(records())
    for patterns, kind, texts, what, why in rows:
        assert patterns, f"row without a path: {what}"
        assert kind in KINDS, f"{patterns}: kind {kind!r} is not one of {sorted(KINDS)}"
        assert what and why, f"{patterns}: every exception says what stays and why"
        for p in patterns:
            assert any(fnmatch.fnmatchcase(t, p) for t in tracked), f"{p} matches no tracked file"
    for path, kind, _ in PENDING:
        assert path in records() and kind in KINDS, (path, kind)


def test_prose_files_have_no_spanish_lines():
    bad = report({"prose"})
    assert not bad, "Spanish prose (translate it, or list it in docs/language-audit.md):\n" + "\n".join(bad)


def test_comments_and_docstrings_of_code_have_no_spanish_lines():
    bad = report({"comments"})
    assert not bad, "Spanish comments or docstrings:\n" + "\n".join(bad)


def test_console_messages_and_help_text_are_english():
    bad = report({"messages"})
    assert not bad, "Spanish console messages or help text:\n" + "\n".join(bad)


def test_every_exception_still_matches_a_spanish_line():
    rules = [(r, "|".join(r[0])) for r in exceptions()] + \
        [(((p,), k, (t,) if t else ()), f"PENDING {p}") for p, k, t in PENDING]
    stale = [label for rule, label in rules if not any(_matches(rule, p, k, t) for p, _, k, t in findings())]
    assert not stale, "exceptions that match no Spanish line any more (remove them):\n" + "\n".join(stale)
