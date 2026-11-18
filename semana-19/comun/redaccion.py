"""Week 19, activity 7: the one redaction for results written to the repository.

- the account in any ARN, and any account ID passed explicitly, become <account>;
- the home directory becomes ~;
- a JWT (three base64url parts, the first starting with eyJ) becomes <token>;
- an email address becomes <correo>.

Other 12-digit numbers stay: they may be data. Applied recursively to dicts, lists and strings.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

CUENTA_EN_ARN = re.compile(r"(arn:aws[a-z-]*:[a-z0-9-]*:[a-z0-9-]*:)(\d{12})(?=:|/)")
JWT = re.compile(r"eyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]+")
CORREO = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def redactar(valor: Any, cuentas: Iterable[str] = ()) -> Any:
    if isinstance(valor, dict):
        return {redactar(k, cuentas): redactar(v, cuentas) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [redactar(v, cuentas) for v in valor]
    if not isinstance(valor, str):
        return valor
    texto = JWT.sub("<token>", valor)
    texto = CUENTA_EN_ARN.sub(r"\1<account>", texto)
    for cuenta in cuentas:
        if re.fullmatch(r"\d{12}", cuenta or ""):
            texto = re.sub(rf"(?<!\d){cuenta}(?!\d)", "<account>", texto)
    texto = CORREO.sub("<correo>", texto)
    return texto.replace(str(Path.home()), "~")
