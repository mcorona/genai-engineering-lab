#!/usr/bin/env python3
"""Figures check for translation PRs: every number in a changed file is the same before and after. Offline, $0.

For each text file that the branch changes (and that exists on both sides), it extracts every number (`0.977`,
`1,815`, `$0.00033`, `2026-11-24`, `9/20`, `p50`…) as a multiset and compares the base version with the new one.
Any number that disappears or appears fails the check, with the file and the numbers. New files and binary files
are skipped, and so are the paths in EXEMPT. A translation keeps every figure, so an English rewrite of a sentence must keep its numbers too.
In CI (`.github/workflows/docs.yml`) the check is skipped for a PR labeled `cifras-nuevas`: one whose new figures
are the point, such as a results report filled from a new measurement. Translation PRs never carry the label.

    python3 docs/check_figures.py --base origin/main    # compares HEAD's tree with the merge base
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter

NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# The only exceptions: CI workflows and the docs/ tooling (glossary, audit, tests) are not translations of evidence,
# and their own changes may add numbers (a pinned version, a regenerated count).
EXEMPT = re.compile(r"^(\.github/workflows/|docs/)")
TEXT = re.compile(r"\.(md|py|sh|yml|yaml|txt|json|toml|tf|sql|mmd|cedar|ipynb)$|(^|/)(\.gitignore|Dockerfile)$")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def show(ref: str, path: str) -> str | None:
    r = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True)
    if r.returncode:
        return None
    try:
        return r.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def numbers(text: str) -> Counter:
    return Counter(NUMBER.findall(text))


def compare(base: str, head: str = "HEAD") -> list[str]:
    merge_base = git("merge-base", base, head).strip()
    changed = git("diff", "--name-only", "--diff-filter=M", merge_base, head).split()
    problems = []
    for path in changed:
        if not TEXT.search(path) or EXEMPT.search(path):
            continue
        old, new = show(merge_base, path), show(head, path)
        if old is None or new is None:
            continue
        a, b = numbers(old), numbers(new)
        if a != b:
            lost = sorted((a - b).elements())
            added = sorted((b - a).elements())
            problems.append(f"{path}: lost {lost[:20]} added {added[:20]}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="origin/main", help="the branch the PR merges into")
    ap.add_argument("--head", default="HEAD")
    args = ap.parse_args()
    problems = compare(args.base, args.head)
    if problems:
        print("Figures changed in translated files:")
        print("\n".join(problems))
        return 1
    print("Figures check: every changed file keeps the same numbers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
