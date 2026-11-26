"""The English prose uses the glossary's terms and the house style. Offline, $0.

The forbidden terms come from the Not column of the term list in docs/glossary.md, so the glossary stays the single
source of truth. The note in parentheses after a term says where the rule applies (the glossary explains them):

- no note, or "(in prose)": the term is not used in prose (this test reads only prose);
- "(alone)": the short form is allowed once the same file has used the full term ("dictionary" after "data dictionary");
- "(for …)": the term is avoided only in one sense ("order (for a purchase order)"). A word does not tell its sense,
  so these entries are not checked here; a reviewer checks them.

A term inside one of the preferred terms is fine ("order" in "purchase order"). Style rules, stated in the glossary
too: no space between a number and "%" ("12 %" → "12%"), and a section on what a result does not cover is titled
"Limitations", not "Limits".

Scanned: the git-tracked Markdown files of class A in docs/language-audit-files.tsv, plus the Markdown files added
after the audit (not in the TSV yet). Skipped: fenced code blocks, inline code spans, link targets, URLs, HTML
comments, and the tables of the glossary's word list and term list (they name the terms on purpose). A recorded key or
label that uses a forbidden term is not prose: quote it in backticks.
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GLOSSARY = ROOT / "docs" / "glossary.md"
AUDIT = ROOT / "docs" / "language-audit-files.tsv"
TEXT = GLOSSARY.read_text(encoding="utf-8")

# Generated text is fixed in its generator, not by hand. Each entry: file → {forbidden term it may still contain:
# why}. test_every_exception_is_still_needed fails once the term is gone, so the entry is removed with the fix.
EXCEPTIONS: dict[str, dict[str, str]] = {
    "docs/language-audit.md": {
        # The inventory between BEGIN and END GENERATED INVENTORY is written by docs/language_audit.py --markdown.
        # Its "First Spanish line" column quotes Spanish source comments verbatim: "golden set de tareas"
        # (semana-13/golden/construir_tareas.py) and "la transacción READ ONLY" (semana-16/tests/
        # test_plugin_auditoria.py). They are quotes, not English prose; the generator could put them in code spans.
        "golden set": "generated: a verbatim quote of a Spanish comment in semana-13/golden/construir_tareas.py",
        "read only": "generated: a verbatim quote of a Spanish comment (SQL READ ONLY) in test_plugin_auditoria.py",
    },
}


def cells(line: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]


def split_outside_parentheses(cell: str) -> list[str]:
    parts, depth, current = [], 0, ""
    for ch in cell:
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    return [p.strip() for p in parts + [current] if p.strip()]


def term_list() -> list[dict]:
    """One entry per term of the Not column: {term, note, use: the row's preferred terms}."""
    section = TEXT.split("## Term list", 1)[1]
    rows = [cells(line) for line in section.splitlines() if line.startswith("|")]
    header = rows[0]
    use_col, not_col = header.index("Use"), header.index("Not")
    entries = []
    for row in rows[2:]:
        use = [re.sub(r"\s*\(.*\)$", "", u) for u in split_outside_parentheses(row[use_col])]
        for item in split_outside_parentheses(row[not_col]):
            m = re.fullmatch(r"(?P<term>[^()]+?)\s*(?:\((?P<note>[^)]*)\))?", item)
            assert m, f"cannot parse the term list entry {item!r}"
            entries.append({"term": m["term"], "note": m["note"] or "", "use": use})
    return entries


TERMS = term_list()


def checked(entry: dict) -> bool:
    note = entry["note"]
    if note in ("", "in prose", "alone"):
        return True
    if note.startswith("for "):
        return False
    raise AssertionError(f"a note this test does not know in the glossary's term list: {entry}")


def term_rx(term: str) -> re.Pattern:
    """A whole-word match, plural included. All-caps terms (PO, DC, HITL) match case-sensitively."""
    body = r"\s+".join(re.escape(w) for w in term.split())
    return re.compile(rf"(?<![\w-]){body}(?:s|es)?(?![\w-])", 0 if term.isupper() else re.I)


RULES = [(e, term_rx(e["term"]), [term_rx(u) for u in e["use"]]) for e in TERMS if checked(e)]
USE = [term_rx(u) for e in TERMS for u in e["use"]]
CODE = "⁣"  # stands in for a code span: an invisible separator, so "cost per `X` call" is not "cost per call"
PERCENT = re.compile(r"\d %")
LIMITS = re.compile(r"^\s*(#{1,6}\s+Limits\b|\*\*Limits[.:]?\*\*|Limits:\s*$)")  # a heading or a heading-like line


def prose_lines(path: str) -> list[tuple[int, str]]:
    """(line number, prose) pairs, with code, link targets, URLs and HTML comments removed."""
    lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
    skip = set()
    if path == "docs/glossary.md":  # the tables of the word list and the term list name the terms on purpose
        start = next(i for i, line in enumerate(lines) if line.startswith("## Word list"))
        skip = {i for i in range(start, len(lines)) if lines[i].startswith("|")}
    out, fence, comment = [], None, False
    for i, line in enumerate(lines):
        if fence:
            if line.lstrip().startswith(fence):
                fence = None
            continue
        m = re.match(r"\s*(```+|~~~+)", line)
        if m:
            fence = m[1]
            continue
        if comment:
            if "-->" not in line:
                continue
            line, comment = line.split("-->", 1)[1], False
        line = re.sub(r"<!--.*?-->", " ", line)
        if "<!--" in line:
            line, comment = line.split("<!--", 1)[0], True
        if i in skip or re.match(r"\s*\[[^\]]+\]:\s", line):  # reference-style link definitions
            continue
        line = re.sub(r"(`+)(?:(?!\1).)+?\1", CODE, line)       # inline code spans
        line = re.sub(r"\]\([^)]*\)", "]", line)                # link targets
        line = re.sub(r"<https?://[^>]*>|https?://\S+", " ", line)
        out.append((i + 1, line))
    return out


def files() -> list[str]:
    tracked = set(subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True,
                                 check=True).stdout.split())
    audited, class_a = set(), set()
    for line in AUDIT.read_text(encoding="utf-8").splitlines()[1:]:
        path, _, cls = line.split("\t")[:3]
        audited.add(path)
        if cls == "A":
            class_a.add(path)
    newer = {p for p in tracked - audited if not re.search(r"(^|/)(vendor|node_modules)/", p)}
    return sorted((class_a & tracked) | newer)


def inside(m: re.Match, line: str, patterns: list[re.Pattern]) -> bool:
    return any(u.start() <= m.start() and m.end() <= u.end() for rx in patterns for u in rx.finditer(line))


def violations(path: str) -> list[str]:
    allowed = EXCEPTIONS.get(path, {})
    found, full_term_seen = [], set()
    for n, line in prose_lines(path):
        for entry, rx, use in RULES:
            if entry["term"] in allowed:
                continue
            for m in rx.finditer(line):
                if inside(m, line, USE):
                    continue
                if entry["note"] == "alone" and (entry["term"] in full_term_seen or any(
                        u.start() < m.start() for r in use for u in r.finditer(line))):
                    continue
                found.append(f"{path}:{n}: {m[0]!r} → {' or '.join(entry['use'])}")
            if any(r.search(line) for r in use):
                full_term_seen.add(entry["term"])
        if m := PERCENT.search(line):
            found.append(f"{path}:{n}: a space before % ({m[0]!r}) → no space")
        if LIMITS.match(line):
            found.append(f"{path}:{n}: the heading 'Limits' → 'Limitations'")
    return found


def test_the_term_list_is_parsed():
    notes = {e["term"]: e["note"] for e in TERMS}
    assert notes["golden set"] == "" and notes["multitenant"] == "" and notes["PO"] == "in prose"
    assert notes["dictionary"] == "alone" and notes["task"].startswith("for ") and notes["order"].startswith("for ")
    assert len(RULES) >= 30


def test_the_glossary_states_the_style_rules():
    assert "(`12%`, not `12 %`)" in TEXT and 'titled "Limitations", not "Limits"' in TEXT


def test_the_scan_skips_code_link_targets_and_the_term_list():
    assert {"README.md", "docs/glossary.md", "docs/exit-criteria.md"} <= set(files())
    # class B and C files are not scanned; the English README next to them is
    assert not any(p.startswith(("semana-12/ingesta/", "semana-13/golden/")) and not p.endswith("/README.md")
                   for p in files())
    glossary = "\n".join(line for _, line in prose_lines("docs/glossary.md"))
    assert "golden dataset" not in glossary and "`" not in glossary and "](" not in glossary
    assert not violations("docs/glossary.md")


def test_every_exception_is_still_needed():
    for path, terms in EXCEPTIONS.items():
        text = "\n".join(line for _, line in prose_lines(path))
        for term in terms:
            assert term_rx(term).search(text), f"{path}: the exception for {term!r} is no longer needed"


@pytest.mark.parametrize("path", files())
def test_prose_uses_the_glossary_terms(path):
    found = violations(path)
    assert not found, "\n".join(found)
