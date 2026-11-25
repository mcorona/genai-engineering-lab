"""Each Spanish shell script that a person runs has an English name next to it, which runs the original. Offline, $0.

docs/script-aliases.tsv lists the pairs. The original keeps its name, because the plans and the recorded logs cite it.
For the weeks the English pass has covered, the test checks that the wrapper exists and is executable, and runs a copy of
it next to a stand-in for the original: the wrapper must pass every argument through unchanged and keep the exit code.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from test_flag_aliases import WEEKS

ROOT = Path(__file__).resolve().parents[2]
PAIRS = [line.split("\t") for line in (ROOT / "docs" / "script-aliases.tsv").read_text(encoding="utf-8").splitlines()[1:]]
COVERED = [(es, en) for es, en in PAIRS if es.split("/")[0] in WEEKS]


def test_every_original_exists():
    assert len(PAIRS) == 17
    for es, en in PAIRS:
        assert (ROOT / es).is_file(), es
        assert Path(es).parent == Path(en).parent, (es, en)


def test_there_are_wrappers_to_check():
    assert len(COVERED) >= 10


@pytest.mark.parametrize("es,en", COVERED)
def test_the_english_name_runs_the_original_with_the_same_arguments(es, en, tmp_path):
    wrapper = ROOT / en
    assert wrapper.is_file(), f"{en} is missing"
    assert os.access(wrapper, os.X_OK), f"{en} is not executable"
    assert f'exec "$(dirname "$0")/{Path(es).name}" "$@"' in wrapper.read_text(encoding="utf-8")
    # A stand-in for the original: it prints its arguments, one per line, and exits with 3.
    shutil.copy(wrapper, tmp_path / Path(en).name)
    stand_in = tmp_path / Path(es).name
    stand_in.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@"\nexit 3\n', encoding="utf-8")
    stand_in.chmod(0o755)
    args = ["--confirm", "two words", "--budget"]
    r = subprocess.run([str(tmp_path / Path(en).name), *args], capture_output=True, text=True)
    assert r.returncode == 3
    assert r.stdout.splitlines() == args
