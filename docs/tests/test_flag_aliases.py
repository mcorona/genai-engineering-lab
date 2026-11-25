"""Every Spanish command-line flag also takes its English alias, and the Spanish name keeps working. Offline, $0.

docs/flag-aliases.tsv maps each Spanish flag to its English alias. For every `add_argument` call in the weeks the
English pass has covered, the test checks three things:

- the Spanish flag is the first option string, so argparse keeps the destination name it had (`--si` -> `args.si`)
  and the code, the tests and the commands recorded in the logs keep working;
- the English alias from the table is on the same call;
- a real argparse parser built from the file's option strings accepts both names and gives them the same destination,
  with no conflict between an alias and another flag of the same script.
"""
import argparse
import re
import ast
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ALIASES = dict(line.split("\t") for line in (ROOT / "docs" / "flag-aliases.tsv").read_text(encoding="utf-8").splitlines()[1:])
UNCHANGED = "(unchanged)"
# The weeks whose scripts already carry the aliases. Step 4 of the English pass adds the rest, group by group.
WEEKS = {f"semana-{n:02d}" for n in range(1, 19)}
# Frozen files: a manifest pins their hash, so they keep their Spanish flags (docs/language-audit.md, exceptions).
FROZEN = {
    "semana-13/golden/construir_tareas.py": "semana-13/golden/manifiesto.json",
    "semana-16/verdad/construir.py": "semana-16/verdad/manifiesto.json",
}


def scripts() -> list[str]:
    out = subprocess.run(["git", "ls-files", "semana-*/**.py", "semana-*/*.py"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.split()
    return sorted({p for p in out if p.split("/")[0] in WEEKS and "/vendor/" not in p and "/.build/" not in p
                   and p not in FROZEN})


def test_the_frozen_files_are_pinned_by_their_manifest():
    for path, manifest in FROZEN.items():
        assert Path(path).name in (ROOT / manifest).read_text(encoding="utf-8"), (path, manifest)


def calls(path: str) -> list[tuple[str, list[str]]]:
    """The literal option strings of each add_argument call in the file, with the parser it is called on."""
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "add_argument":
            opts = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if opts and opts[0].startswith("-"):
                out.append((ast.unparse(node.func.value), opts))
    return out


def test_the_table_maps_every_spanish_flag_once():
    assert len(ALIASES) == 136
    english = [en for en in ALIASES.values() if en != UNCHANGED]
    assert all(en.startswith("--") and en == en.lower() for en in english)
    # Two Spanish spellings of the same idea may share an alias; nothing else does.
    shared = {en for en in english if english.count(en) > 1}
    assert shared == {"--no-history"}, shared


def test_there_are_scripts_to_check():
    assert len([p for p in scripts() if calls(p)]) >= 60


@pytest.mark.parametrize("path", [p for p in scripts() if calls(p)])
def test_each_spanish_flag_has_its_english_alias(path):
    parsers: dict[str, argparse.ArgumentParser] = {}
    for owner, opts in calls(path):
        parser = parsers.setdefault(owner, argparse.ArgumentParser(add_help=False))
        spanish = [o for o in opts if o in ALIASES]
        for es in spanish:
            assert opts[0] == es, f"{path}: {opts}: the Spanish flag must come first, so the destination keeps its name"
            en = ALIASES[es]
            if en != UNCHANGED:
                assert en in opts, f"{path}: {es} has no English alias {en}"
        action = parser.add_argument(*opts)  # raises on a conflict between two flags of the same parser
        if spanish:
            assert action.dest == spanish[0].lstrip("-").replace("-", "_")
            for name in opts:
                assert parser._option_string_actions[name] is action


# ---------- shell scripts: `case` patterns (`--detener|--stop)`) and `[ "$a" = "--x" ]` tests ----------
CASE = re.compile(r"^\s*\(?((?:--?[\w-]+\|)*--?[\w-]+)\)", re.M)
TEST_EQ = re.compile(r"""\[\s*"\$\w+"\s*==?\s*"(--[\w-]+)"\s*\]""")


def shell_scripts() -> list[str]:
    out = subprocess.run(["git", "ls-files", "semana-*/**.sh", "semana-*/*.sh"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.split()
    return sorted({p for p in out if p.split("/")[0] in WEEKS and "/vendor/" not in p and "/.build/" not in p})


@pytest.mark.parametrize("path", shell_scripts())
def test_each_spanish_shell_option_has_its_english_alias(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    for group in CASE.findall(text):
        names = group.split("|")
        for es in (n for n in names if n in ALIASES and ALIASES[n] != UNCHANGED):
            assert ALIASES[es] in names, f"{path}: the pattern {group}) has no {ALIASES[es]}"
    lone = [f for f in TEST_EQ.findall(text) if f in ALIASES and ALIASES[f] != UNCHANGED]
    assert not lone, f"{path}: {lone} is matched alone; use a case pattern with its English alias"
