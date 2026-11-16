"""Week 19, activity 6: the RDS CA bundle packaged with the loader and the tools Lambda is the official us-east-1 bundle.

Source: https://truststore.pki.rds.amazonaws.com/us-east-1/us-east-1-bundle.pem (fetched 2026-11-16). The SHA-256 is
pinned here: any change to the file must be a deliberate, reviewed update of this value.
"""
from __future__ import annotations

import hashlib
import ssl
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
HUELLA = "b1711d12bae51838581281e23b6cb97b1074016873b4dafc80ed14002462dd77"
COPIAS = [S19 / "infra" / "loader" / "rds-ca.pem", S19 / "herramientas" / "rds-ca.pem"]


@pytest.mark.parametrize("ruta", COPIAS, ids=lambda p: str(p.relative_to(S19)))
def test_bundle_es_el_oficial_fijado_por_huella(ruta):
    assert hashlib.sha256(ruta.read_bytes()).hexdigest() == HUELLA


@pytest.mark.parametrize("ruta", COPIAS, ids=lambda p: str(p.relative_to(S19)))
def test_bundle_carga_como_contexto_de_confianza(ruta):
    ctx = ssl.create_default_context(cafile=str(ruta))
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert len(ctx.get_ca_certs()) == 3
