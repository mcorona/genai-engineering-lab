"""Every relative link in the repository's Markdown resolves. Offline, $0.

The documentation was moved from Spanish to English, and files were renamed and split along the way. A link that
points to a path that no longer exists, or to a heading whose text (and so its anchor) changed, fails silently on
GitHub: the reader gets a 404 or lands at the top of the page. This test finds those links before a reader does.

For every git-tracked `*.md` file (except under `vendor/` and `node_modules/`), it reads:

- inline links and images: `[text](target)`, `![alt](target)`;
- reference-style links: the target of every definition `[label]: target`;
- HTML: `<img src="...">` and `<a href="...">`.

A target must be a tracked file, or a folder that holds tracked files (checked against `git ls-files`, so the case
must match, as on GitHub). A `#anchor` must match a heading of the target Markdown file, slugged as GitHub does
(lowercase, punctuation other than `-` and `_` removed, spaces to `-`, repeated headings get `-1`, `-2`...), or an
explicit `<a id="...">` / `<a name="...">`. An anchor on a folder is checked against its README.md; an anchor on a
file that is not Markdown (such as `#L10`) is not checked. External URLs (http, https, mailto...) are skipped, except
those into this repository (https://github.com/mcorona/genai-engineering-lab/blob/main/...), whose path is checked,
and the repository's workflow pages and badges (.../actions/workflows/NAME.yml), whose workflow must exist.

Links inside fenced code blocks, code spans and HTML comments are ignored: they are examples, not links.

Some broken links cannot be fixed: they are in recorded evidence (class C in docs/language-audit-files.tsv) or in a
report a script writes, so editing the file would falsify the record or be undone by the next run. They are listed in
EXCEPTIONS with the reason, and an exception that no longer fails is reported, so the list does not go stale.
"""
import re
import subprocess
from functools import cache
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPO_URL = re.compile(r"https?://github\.com/mcorona/genai-engineering-lab/(?:blob|tree)/main/([^?#]*)(.*)", re.I)
WORKFLOW_URL = re.compile(r"https?://github\.com/mcorona/genai-engineering-lab/actions/workflows/([^/?#]+)", re.I)
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")

# (file, target as written) -> why the broken link stays. Only for links that cannot be edited: recorded evidence
# (class C in docs/language-audit-files.tsv) or a report a script writes. Empty: every link resolved when this test
# was added (766 links in 324 files).
EXCEPTIONS: dict[tuple[str, str], str] = {
}


def git_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p]


TRACKED = set(git_files())
FOLDERS = {str(parent) for p in TRACKED for parent in PurePosixPath(p).parents if str(parent) != "."}
MARKDOWN = sorted(p for p in TRACKED if p.endswith(".md") and not re.search(r"(^|/)(vendor|node_modules)/", p))


# --- Reading Markdown --------------------------------------------------------------------------------------------

def blank(match: re.Match) -> str:
    """Replace a match with its newlines only, so line numbers stay right."""
    return "\n" * match.group(0).count("\n")


def without_code(text: str) -> str:
    """The text with fenced code blocks, HTML comments and code spans blanked out."""
    text = "\n".join(line if keep else "" for line, keep in zip(text.split("\n"), code_mask(text)))
    text = re.sub(r"<!--.*?-->", blank, text, flags=re.S)
    # A code span: a run of backticks closed by a run of the same length, within one paragraph.
    return re.sub(r"(?<!`)(`+)(?!`)(?:(?!\n[ \t]*\n).)+?(?<!`)\1(?!`)", blank, text, flags=re.S)


INLINE = re.compile(r"\]\(\s*(<[^>\n]*>|(?:[^()\s]|\([^()\s]*\))*)(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)")
DEFINITION = re.compile(r"^ {0,3}\[([^\]]+)\]:\s*(<[^>\n]*>|\S+)", re.M)
HTML = re.compile(r"<(?:img|a)\b[^>]*?\b(?:src|href)\s*=\s*([\"'])(.*?)\1", re.I | re.S)


def links(path: str) -> list[tuple[int, str]]:
    """(line, target) for every link in a Markdown file, outside code."""
    text = without_code((ROOT / path).read_text(encoding="utf-8"))
    line = lambda m: text.count("\n", 0, m.start()) + 1  # noqa: E731
    found = [(line(m), m.group(1)) for m in INLINE.finditer(text)]
    found += [(line(m), m.group(2)) for m in DEFINITION.finditer(text)]
    found += [(line(m), m.group(2)) for m in HTML.finditer(text)]
    return sorted((n, t.strip().removeprefix("<").removesuffix(">")) for n, t in found)


# --- Anchors -----------------------------------------------------------------------------------------------------

def slug(heading: str) -> str:
    """GitHub's anchor for a heading: the rendered text, lowercase, punctuation but `-` and `_` removed, spaces to `-`."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", heading)          # links and images keep their text
    text = re.sub(r"<[^>]+>", "", text)                                  # HTML tags
    text = re.sub(r"(\*+|(?<!\w)_+|_+(?!\w))", "", text)                 # emphasis markers
    text = text.replace("`", "").strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


@cache
def anchors(path: str) -> frozenset[str]:
    """The anchors a Markdown file defines: its headings (ATX and setext) and explicit `<a id/name>`."""
    raw = (ROOT / path).read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->", blank, raw, flags=re.S)
    lines = [line if keep else "" for line, keep in zip(text.split("\n"), code_mask(text))]
    headings = []
    for i, line in enumerate(lines):
        atx = re.match(r"^ {0,3}#{1,6}(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$", line)
        if atx:
            headings.append(atx.group(1) or "")
        elif (i > 0 and lines[i - 1].strip() and re.match(r"^ {0,3}(=+|-+)[ \t]*$", line)
              and not re.match(r"^ {0,3}([-*+]|\d+[.)])\s|^ {0,3}(\||#)", lines[i - 1])
              and (i < 2 or not lines[i - 2].strip())):
            headings.append(lines[i - 1].strip())
    found, seen = set(), {}
    for heading in headings:
        base = slug(heading)
        n = seen.get(base, 0)
        seen[base] = n + 1
        found.add(base if n == 0 else f"{base}-{n}")
    found |= {m.group(2) for m in re.finditer(r"<a\s[^>]*\b(id|name)\s*=\s*[\"']([^\"']+)[\"']", raw, re.I)}
    return frozenset(found)


def code_mask(text: str) -> list[bool]:
    """True for each line outside a fenced code block."""
    mask, fence = [], None
    for line in text.split("\n"):
        opener = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence is None and opener:
            fence = opener.group(1)
            mask.append(False)
        elif fence is not None:
            if re.match(rf"^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$", line):
                fence = None
            mask.append(False)
        else:
            mask.append(True)
    return mask


# --- Resolving ---------------------------------------------------------------------------------------------------

def problem(source: str, target: str) -> str | None:
    """Why `target`, written in `source`, does not resolve; None when it does (or is external)."""
    repo, workflow = REPO_URL.match(target), WORKFLOW_URL.match(target)
    if workflow:                                                     # a workflow's page or badge
        name = f".github/workflows/{workflow.group(1)}"
        return None if name in TRACKED else f"{name} is not a tracked workflow"
    if repo:
        path, rest = repo.group(1), repo.group(2)
        resolved = str(PurePosixPath(unquote(path))).strip("/") if path.strip("/") else ""
        fragment = rest.split("#", 1)[1] if "#" in rest else None
    elif SCHEME.match(target) or target.startswith("//"):
        return None
    else:
        path, _, fragment = target.partition("#")
        fragment = fragment if "#" in target else None
        path = unquote(path.split("?", 1)[0])
        if not path:
            resolved = source
        else:
            base = PurePosixPath() if path.startswith("/") else PurePosixPath(source).parent
            parts: list[str] = []
            for part in (base / path.lstrip("/")).parts:
                if part == "..":
                    if not parts:
                        return "goes above the repository root"
                    parts.pop()
                elif part != ".":
                    parts.append(part)
            resolved = "/".join(parts)
    if resolved and resolved not in TRACKED and resolved not in FOLDERS:
        return f"{resolved or '.'} is not a tracked file or folder"
    if not fragment:
        return None
    page = resolved if resolved in TRACKED else f"{resolved}/README.md".lstrip("/")
    if not page.endswith(".md"):
        return None                                                  # e.g. #L10 on a source file
    if page not in TRACKED:
        return f"#{fragment}: {resolved or '.'} has no README.md to hold the anchor"
    if unquote(fragment) not in anchors(page) and unquote(fragment).lower() not in anchors(page):
        return f"#{fragment} is not a heading or anchor of {page}"
    return None


def failures(path: str) -> list[tuple[str, str]]:
    """(target, message) for every link of `path` that does not resolve."""
    out = [(target, f"line {n}: ({target}) {why}") for n, target in links(path) if (why := problem(path, target))]
    return out


@pytest.mark.parametrize("path", MARKDOWN)
def test_every_relative_link_resolves(path):
    broken = [message for target, message in failures(path) if (path, target) not in EXCEPTIONS]
    assert not broken, f"{path} has {len(broken)} broken link(s):\n" + "\n".join(broken)


def test_every_exception_is_still_broken():
    stale = [f"{path}: {target}" for path, target in EXCEPTIONS
             if path not in TRACKED or target not in {t for t, _ in failures(path)}]
    assert not stale, "these exceptions now resolve or their file is gone; remove them:\n" + "\n".join(stale)


def test_the_checker_catches_what_it_should():
    assert slug("Weeks at a glance") == "weeks-at-a-glance"
    assert slug("1. Scope: in & out (v1)") == "1-scope-in--out-v1"
    assert slug("`semana-20/` and [ADR 0014](x.md)") == "semana-20-and-adr-0014"
    assert slug("**Bold** _it_ snake_case") == "bold-it-snake_case"
    assert without_code("a `[x](nope.md)` b\n```\n[y](nope.md)\n```\n") == "a  b\n\n\n\n"
    assert problem("README.md", "docs/glossary.md") is None
    assert problem("README.md", "docs/") is None
    assert problem("README.md", "https://example.com/missing") is None
    assert problem("README.md", "docs/missing.md")
    assert problem("README.md", "#weeks-at-a-glance") is None
    assert problem("README.md", "#no-such-heading")
    assert problem("docs/glossary.md", "../README.md#weeks-at-a-glance") is None
    assert problem("README.md", "https://github.com/mcorona/genai-engineering-lab/blob/main/docs/glossary.md") is None
    assert problem("README.md", "https://github.com/mcorona/genai-engineering-lab/blob/main/docs/missing.md")
    assert problem("README.md", "https://github.com/mcorona/genai-engineering-lab/actions/workflows/docs.yml") is None
    assert problem("README.md", "https://github.com/mcorona/genai-engineering-lab/actions/workflows/gone.yml")
