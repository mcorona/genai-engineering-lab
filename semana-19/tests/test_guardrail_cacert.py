"""Week 19, activity 5: the guardrail creator's vendored botocore has its certificate bundle, offline ($0).

Without it, every Bedrock call from the custom resource fails with 'SSL validation failed ... [Errno 2]'. The bundle is
the one shipped with botocore 1.43.122 (public CA list, not a credential). Its SHA-256 is pinned: a change needs a review.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
BUNDLE = S19 / "guardrail" / "vendor" / "botocore" / "cacert.pem"
HUELLA = "4658f1ddf2d0a9e70c8f760323704c8fb9c0bf2f1f1e7d2dbc5939ca04ea2612"


def test_bundle_del_creador_existe_y_es_el_fijado():
    assert BUNDLE.exists()
    assert hashlib.sha256(BUNDLE.read_bytes()).hexdigest() == HUELLA


def test_bundle_tiene_certificados_de_ca():
    assert BUNDLE.read_text(encoding="utf-8").count("BEGIN CERTIFICATE") == 126


def test_botocore_vendorizado_busca_el_bundle_en_su_carpeta():
    httpsession = (S19 / "guardrail" / "vendor" / "botocore" / "httpsession.py").read_text(encoding="utf-8")
    assert "DEFAULT_CA_BUNDLE = os.path.join(os.path.dirname(__file__), 'cacert.pem')" in httpsession
