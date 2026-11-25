"""The figures check finds every number, so a translation that changes one fails. Offline, $0."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_figures import numbers  # noqa: E402


def test_numbers_are_extracted_whole():
    assert numbers("USD 0.47 per 1,000 queries, p95 10.9 s, 9/20 on 2026-11-24") == numbers(
        "0.47 1,000 95 10.9 9 20 2026 11 24")


def test_a_translation_that_keeps_the_figures_passes():
    assert numbers("Se aceptaron 220 de 229 (96.1 %).") == numbers("220 of 229 were accepted (96.1%).")


def test_a_changed_figure_fails():
    assert numbers("latencia p50 de 52.4 s") != numbers("p50 latency of 52.5 s")
    assert numbers("3 runs") != numbers("three runs")


def test_an_english_flag_alias_is_not_a_figure():
    assert numbers('case --solo-actividad7) A7=1 ;;') == numbers('case --solo-actividad7|--activity7-only) A7=1 ;;')
    assert numbers("--solo-actividad7") != numbers("--solo-actividad8")
