"""Week 20, activity 3: the agent's prompt-cache mode is chosen at synth time (CACHE_PROMPT, CACHE_TTL; ADR 0014), and
the defaults (off, 5m) leave the week 19 template unchanged.

Runs in the spike-iac job (needs aws-cdk-lib). Synthesizes lab with COMPUTO=1 and reads the agent function's
environment from the semana19-computo template, as test_infra_presupuesto.py does."""
from __future__ import annotations

import pytest

from test_infra_presupuesto import _entorno_del_agente, _sintetizar  # noqa: F401  (same synth helpers)

import os


def _con(variables: dict):
    viejas = {k: os.environ.pop(k, None) for k in ("CACHE_PROMPT", "CACHE_TTL")}
    os.environ.update(variables)
    try:
        return _sintetizar(None)
    finally:
        for k in ("CACHE_PROMPT", "CACHE_TTL"):
            os.environ.pop(k, None)
            if viejas[k] is not None:
                os.environ[k] = viejas[k]


@pytest.mark.parametrize("variables, esperado", [
    ({}, {}),
    ({"CACHE_PROMPT": "off", "CACHE_TTL": "5m"}, {}),
    ({"CACHE_PROMPT": "historial"}, {"CACHE_PROMPT": "historial"}),
    ({"CACHE_PROMPT": "historial", "CACHE_TTL": "1h"}, {"CACHE_PROMPT": "historial", "CACHE_TTL": "1h"}),
])
def test_la_cache_llega_al_agente_solo_si_no_es_la_de_omision(variables, esperado):
    r = _con(variables)
    assert r.returncode == 0, r.stderr[-2000:]
    entorno = _entorno_del_agente(r.salida)
    assert {k: entorno[k] for k in ("CACHE_PROMPT", "CACHE_TTL") if k in entorno} == esperado


def test_un_modo_desconocido_detiene_la_sintesis():
    r = _con({"CACHE_PROMPT": "todo"})
    assert r.returncode != 0 and "unknown CACHE_PROMPT" in r.stderr
