"""The English glosses of week 11's reference review keep every figure of the Spanish cells they translate. Offline, $0.

semana-11/resultados/revision_referencias.md quotes the frozen eval set verbatim, so its Spanish cells stay in Spanish.
revision_referencias_en.md glosses them by row; a gloss must carry exactly the numbers of its original cell.
"""
import re
from collections import Counter
from pathlib import Path

RES = Path(__file__).resolve().parents[2] / "semana-11" / "resultados"
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def rows(path: Path) -> dict[str, list[str]]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        if cells and cells[0].isdigit():
            out[cells[0]] = cells
    return out


def test_every_gloss_keeps_the_figures_of_its_cell():
    original, glosses = rows(RES / "revision_referencias.md"), rows(RES / "revision_referencias_en.md")
    assert len(original) == 20 and len(glosses) == 18
    for n, (_, ident, question, passage, reference) in glosses.items():
        src = original[n]
        assert src[1] == ident, n
        for gloss, cell in ((question, src[3]), (passage, src[4]), (reference, src[5])):
            if gloss == "(in English)":
                continue
            assert Counter(NUMBER.findall(gloss)) == Counter(NUMBER.findall(cell)), (n, gloss, cell)


def test_only_the_rows_entirely_in_english_have_no_gloss():
    original, glosses = rows(RES / "revision_referencias.md"), rows(RES / "revision_referencias_en.md")
    assert sorted(set(original) - set(glosses), key=int) == ["11", "19"]
    assert all(original[n][2] == "en" for n in ("11", "19"))
