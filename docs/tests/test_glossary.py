"""The glossary is linked wherever its terms are used, and the English index of weeks is complete. Offline, $0.

- Every README in the repository that uses a term from docs/glossary.md links the glossary, with a link that resolves.
- Every `semana-NN/` folder has a row in the root README's "Weeks at a glance" table.
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GLOSSARY = ROOT / "docs" / "glossary.md"
GLOSSARY_URL = "https://github.com/mcorona/genai-engineering-lab/blob/main/docs/glossary.md"
TEXT = GLOSSARY.read_text(encoding="utf-8")


def glossary_terms() -> set[str]:
    """Spanish terms: the code spans in the first column of each table, plus the Spanish words of the word list."""
    terms: set[str] = set()
    body = TEXT.split("## Term list", 1)[0]               # the term list holds English terms
    word_list = body.split("## Word list", 1)[1]
    for line in body.split("## Word list", 1)[0].splitlines():
        if line.startswith("| ") and not line.startswith("|---"):
            first = line.split("|")[1]
            for span in re.findall(r"`([^`]+)`", first):
                term = span.strip().strip("/").split("/")[-1]
                if re.fullmatch(r"[A-Za-z_][\w-]*[A-Za-z0-9]", term) and "NN" not in term and not term.startswith("-"):
                    terms.add(term)
    for line in word_list.splitlines():
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) == 6 and cells[0] not in ("Spanish", "---"):
            for spanish in cells[0::2]:
                terms.update(w for w in re.findall(r"[a-zñ]{4,}", spanish))
    return terms


# Glossary entries that are also ordinary English words or product names: matching them would flag English text.
ENGLISH = {"base", "simple", "sql", "total", "gold", "question", "lang", "shadowing", "ok", "adr", "eval", "guardrail",
           "guardrails", "datasets", "infra", "golden", "legacy", "rug_pull"}
TERMS = glossary_terms() - ENGLISH
TERM_RX = re.compile(r"(?<![\w-])(" + "|".join(sorted(map(re.escape, TERMS), key=len, reverse=True)) + r")(?![\w-])")
WEEK_RX = re.compile(r"\bsemana-\d\d\b")


def readmes() -> list[str]:
    out = subprocess.run(["git", "ls-files", "*README*.md", "README.md", "semana-20/Fas5Sema20.md"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split()
    return sorted({p for p in out if not re.search(r"(^|/)(vendor|node_modules)/", p)})


def test_the_glossary_has_terms():
    assert {"semana", "resultados", "respondida", "PENDING_APPROVAL", "artmst", "quedan", "semana19-control"} <= TERMS
    assert len(TERMS) > 400


@pytest.mark.parametrize("readme", readmes())
def test_a_readme_that_uses_a_glossary_term_links_the_glossary(readme):
    text = (ROOT / readme).read_text(encoding="utf-8")
    used = sorted(set(TERM_RX.findall(text)) | set(WEEK_RX.findall(text)))
    if not used:
        return
    links = re.findall(r"\]\(([^)\s]*glossary\.md)(?:#[^)]*)?\)", text)
    assert links, f"{readme} uses glossary terms ({', '.join(used[:5])}…) but does not link docs/glossary.md"
    for link in links:
        if link.startswith("http"):
            assert link == GLOSSARY_URL, f"{readme}: {link}"
        else:
            assert (ROOT / readme).parent.joinpath(link).resolve() == GLOSSARY, f"{readme}: {link} does not resolve"


def test_weeks_at_a_glance_lists_every_week():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    table = readme.split("### Weeks at a glance", 1)[1].split("\n### ", 1)[0]
    listed = set(re.findall(r"\[`(semana-\d\d)/`\]\((semana-\d\d)/", table))
    folders = sorted(p.name for p in ROOT.glob("semana-[0-9][0-9]") if p.is_dir())
    assert [a for a, b in sorted(listed) if a == b] == folders
    for target in re.findall(r"\]\((semana-\d\d/[^)]+)\)", table):
        assert (ROOT / target).is_file(), target


def test_the_glossary_anchor_in_the_root_readme_exists():
    assert "(../README.md#weeks-at-a-glance)" in TEXT
    assert "\n### Weeks at a glance\n" in (ROOT / "README.md").read_text(encoding="utf-8")
