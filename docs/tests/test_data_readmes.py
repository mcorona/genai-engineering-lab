"""Every Spanish data file and every recorded result has an English description next to it. Offline, $0.

The audit (docs/language-audit-files.tsv) marks Spanish evaluation data as class B and recorded evidence as class C.
Neither is translated: translating a corpus or a gold set would change the experiment, and editing a recorded output
would falsify it. Instead, each data or results folder gets an English README.md, and the files that sit outside such
a folder are described in their week's data guide, docs/data/semana-NN.md. Each of those documents has:

- a `## Files` table whose first column lists glob patterns (`casos.jsonl`, `eval_*.json`, `corridas/**`), relative
  to the folder the document describes: a README's own folder, or the week folder for a data guide (`*` stays inside
  one folder, `**` crosses folders);
- optionally, a `## Keys` table whose first column lists the Spanish keys of the files, with their English meaning.

The test checks four things:

- each document in DOCS exists and links the glossary;
- every class B or C file of the audit is matched by a pattern of a document in one of its parent folders;
- every tracked file in a README's folder is matched by one of its patterns, and every pattern matches a file;
- every key in a Keys table appears in at least one file the document covers.

Some data folders get no README of their own, because code reads every Markdown file in them (`semana-08/corpus`,
`semana-09/corpus_beta`, `semana-10/fuentes`) or hashes every file in them (`semana-12/ingesta/paquete`), or because
they are part of a packaged plugin or a deployed asset. Their week's data guide describes them. The guides live in
docs/data/ and not in the week folders because the paid eval workflows run on any change in a week folder except a
README.md.
"""
from __future__ import annotations

import re
import subprocess
from functools import cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GLOSSARY = ROOT / "docs" / "glossary.md"

# A README.md inside the folder it describes.
READMES = [
    "semana-02/corridas",
    "semana-02/resultados-n5",
    "semana-03/data",
    "semana-03/resultados",
    "semana-04/entrenamiento/data",
    "semana-04/entrenamiento/destilacion",
    "semana-04/entrenamiento/dpo",
    "semana-04/resultados",
    "semana-05/prompts",
    "semana-05/resultados",
    "semana-06/baseline",
    "semana-06/golden",
    "semana-06/resultados",
    "semana-06/rubricas",
    "semana-07/datasets",
    "semana-07/resultados",
    "semana-08/datasets",
    "semana-08/resultados",
    "semana-09/datasets",
    "semana-09/resultados",
    "semana-10/datasets",
    "semana-10/escaneos",
    "semana-10/imagenes",
    "semana-10/imagenes_inyeccion",
    "semana-10/legado",
    "semana-10/pdf",
    "semana-10/pdf_inyeccion",
    "semana-10/resultados",
    "semana-11/datasets",
    "semana-11/resultados",
    "semana-12/resultados",
    "semana-13/golden",
    "semana-13/resultados",
    "semana-14/resultados",
    "semana-15/resultados",
    "semana-16/resultados",
    "semana-16/verdad",
    "semana-17/resultados",
    "semana-17/trayectorias",
    "semana-19/resultados",
    "semana-19/seguridad/kb_envenenados",
    "semana-20/resultados",
]
# A week's data guide, docs/data/semana-NN.md: the data and evidence files outside the folders above.
GUIDES = [
    "semana-01",
    "semana-02",
    "semana-03",
    "semana-04",
    "semana-07",
    "semana-08",
    "semana-09",
    "semana-10",
    "semana-12",
    "semana-13",
    "semana-14",
    "semana-16",
    "semana-18",
    "semana-19",
]
DOCS = [f"{d}/README.md" for d in READMES] + [f"docs/data/{w}.md" for w in GUIDES]


def base(doc: str) -> str:
    """The folder a document describes: its own folder for a README, the week folder for a data guide."""
    return Path(doc).stem if doc.startswith("docs/data/") else str(Path(doc).parent)


@cache
def tracked() -> tuple[str, ...]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return tuple(out.splitlines())


def to_regex(pattern: str) -> re.Pattern:
    out = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out + r"\Z")


def table(text: str, heading: str) -> list[str]:
    """The first-column entries of the table under `## heading`, without their backticks."""
    parts = re.split(rf"^## {re.escape(heading)}\s*$", text, maxsplit=1, flags=re.M)
    if len(parts) < 2:
        return []
    section = re.split(r"^## ", parts[1], maxsplit=1, flags=re.M)[0]
    rows = [line for line in section.splitlines() if line.startswith("|")][2:]  # skip header and separator
    out = []
    for row in rows:
        first = row.split("|")[1].strip()
        out += re.findall(r"`([^`]+)`", first)
    return out


@cache
def patterns(doc: str) -> tuple[str, ...]:
    return tuple(table((ROOT / doc).read_text(encoding="utf-8"), "Files"))


def covered_files(doc: str) -> list[str]:
    folder = base(doc)
    regexes = [to_regex(p) for p in patterns(doc)]
    return [f for f in tracked() if f.startswith(folder + "/") and f != doc
            and any(r.match(f[len(folder) + 1:]) for r in regexes)]


def audit_files(cls: str) -> list[str]:
    rows = (ROOT / "docs" / "language-audit-files.tsv").read_text(encoding="utf-8").splitlines()[1:]
    present = set(tracked())
    return [r.split("\t")[0] for r in rows if r.split("\t")[2] == cls and r.split("\t")[0] in present]


def test_there_are_documents_to_check():
    assert len(DOCS) == len(set(DOCS)) >= 50


def test_the_index_lists_every_data_guide():
    index = (ROOT / "docs" / "data" / "README.md").read_text(encoding="utf-8")
    listed = set(re.findall(r"\]\((semana-\d\d)\.md\)", index))
    assert listed == set(GUIDES), listed ^ set(GUIDES)
    on_disk = {p.stem for p in (ROOT / "docs" / "data").glob("semana-*.md")}
    assert on_disk == set(GUIDES), on_disk ^ set(GUIDES)


@pytest.mark.parametrize("doc", DOCS)
def test_each_document_exists_and_links_the_glossary(doc):
    path = ROOT / doc
    assert path.is_file(), f"{doc} is missing"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# "), f"{doc}: the first line is the title"
    links = re.findall(r"\]\(([^)\s#]*glossary\.md)", text)
    assert links and all(path.parent.joinpath(l).resolve() == GLOSSARY for l in links), f"{doc}: glossary link"
    assert patterns(doc), f"{doc}: no `## Files` table"


@pytest.mark.parametrize("cls", ["B", "C"])
def test_every_data_and_evidence_file_is_described(cls):
    missing = []
    for f in audit_files(cls):
        docs = [d for d in DOCS if f.startswith(base(d) + "/")]
        if not any(f in covered_files(d) for d in docs):
            missing.append(f)
    assert not missing, f"{len(missing)} class {cls} files with no English description: {missing[:15]}"


@pytest.mark.parametrize("doc", [d for d in DOCS if d.endswith("README.md")])
def test_a_readme_describes_every_file_in_its_folder(doc):
    folder = base(doc)
    inside = [f for f in tracked() if f.startswith(folder + "/") and f != doc]
    covered = set(covered_files(doc))
    assert not [f for f in inside if f not in covered], f"{doc}: files not described"


@pytest.mark.parametrize("doc", DOCS)
def test_every_pattern_matches_a_file(doc):
    folder = base(doc)
    names = [f[len(folder) + 1:] for f in tracked() if f.startswith(folder + "/")]
    stale = [p for p in patterns(doc) if not any(to_regex(p).match(n) for n in names)]
    assert not stale, f"{doc}: patterns that match no file: {stale}"


@pytest.mark.parametrize("doc", DOCS)
def test_every_listed_key_is_in_the_files(doc):
    keys = table((ROOT / doc).read_text(encoding="utf-8"), "Keys")
    if not keys:
        return
    text = ""
    for f in covered_files(doc):
        try:
            text += (ROOT / f).read_text(encoding="utf-8") + "\n"
        except (UnicodeDecodeError, IsADirectoryError):
            continue
    absent = [k for k in keys if not re.search(rf"(?<![\w]){re.escape(k)}(?![\w])", text)]
    assert not absent, f"{doc}: keys that appear in none of its files: {absent}"
