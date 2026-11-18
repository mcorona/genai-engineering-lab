"""Shared pytest settings for week 19 tests."""


def pytest_configure(config):
    # "vivo" marks tests that need a local throwaway database (never the lab). CI deselects them with -m "not vivo".
    config.addinivalue_line("markers", "vivo: live test that needs a local throwaway database (S19_DSN_LOCAL)")


def _preparar_paquete_agente() -> None:
    """Synthesis needs the agent asset folder. Tests use the layout without dependencies (never deployed)."""
    import os
    import sys
    from pathlib import Path

    S19 = Path(__file__).resolve().parents[1]
    os.environ.setdefault("S19_SIN_DEPENDENCIAS", "1")
    # The package layout puts the code under app/ (paquete_agente.CODIGO). Checking the old top-level folder made every
    # test run rebuild the layout without dependencies and wipe a deployable package.
    sys.path.insert(0, str(S19 / "infra"))
    import paquete_agente
    if not paquete_agente.disposicion_presente():
        paquete_agente.construir(sin_dependencias=True)


_preparar_paquete_agente()
