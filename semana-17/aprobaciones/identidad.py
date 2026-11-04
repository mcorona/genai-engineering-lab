"""Week 17, activity 6: who is deciding. The approver's identity comes from a verified access token, never from the request.

Same posture as the week 14 server (`semana-14/servidor/oauth.py::VerificadorJWT`): an algorithm allowlist checked before anything,
`exp`, `iat`, `iss`, `aud` and `sub` required, access tokens only. The audience is the approvals service's own resource, so a token
minted for the MCP server cannot be replayed here. The roles are the realm roles (`realm_access.roles`), as Keycloak issues them.

`EmisorDePrueba` signs tokens with an ephemeral RSA key: the simulated approver of the evaluation and the tests (Keycloak is not
needed to exercise the checks; the realm file declares the same roles and users, `semana-14/auth/realm/legacybridge-realm.json`).
"""
from __future__ import annotations

import time
import uuid

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from .maquina import Identidad

AUDIENCIA = "legacybridge-aprobaciones"
EMISOR_LAB = "http://localhost:8180/realms/legacybridge"


class ErrorToken(Exception):
    """The token cannot be trusted. The message is for the operator; the caller only learns `token_invalido`."""


class VerificadorAprobador:
    """`clave` is either a public key (tests, the simulated approver) or a `jwt.PyJWKClient` over the realm's JWKS (live Keycloak)."""

    def __init__(self, clave, *, emisor: str = EMISOR_LAB, audiencia: str = AUDIENCIA, algoritmos=("RS256",), margen_s: int = 30):
        self.clave, self.emisor, self.audiencia, self.algoritmos, self.margen_s = clave, emisor, audiencia, tuple(algoritmos), margen_s

    def verificar(self, token: str) -> Identidad:
        try:
            cabecera = jwt.get_unverified_header(token)
        except jwt.PyJWTError as e:
            raise ErrorToken(f"malformed: {type(e).__name__}") from None
        if cabecera.get("alg") not in self.algoritmos:            # none, HS256 and anything else are refused before any key is used
            raise ErrorToken(f"algorithm not allowed: {cabecera.get('alg')!r}")
        clave = self.clave.get_signing_key_from_jwt(token).key if isinstance(self.clave, jwt.PyJWKClient) else self.clave
        try:
            c = jwt.decode(token, clave, algorithms=list(self.algoritmos), audience=self.audiencia, issuer=self.emisor,
                           leeway=self.margen_s, options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        except jwt.PyJWTError as e:
            raise ErrorToken(type(e).__name__) from None
        if c.get("typ", "Bearer") != "Bearer":
            raise ErrorToken(f"token type not allowed: {c.get('typ')!r}")
        roles = (c.get("realm_access") or {}).get("roles") or []
        if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
            raise ErrorToken("realm_access.roles is not a list of strings")
        return Identidad(str(c["sub"]), tuple(sorted(roles)))


class EmisorDePrueba:
    """Signs access tokens with an ephemeral RSA key. `verificador()` trusts only this key."""

    def __init__(self, emisor: str = EMISOR_LAB, audiencia: str = AUDIENCIA):
        self._llave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.emisor, self.audiencia = emisor, audiencia

    def token(self, sub: str, roles=(), *, vida_s: int = 300, audiencia: str | None = None, emisor: str | None = None,
              typ: str = "Bearer", ahora: float | None = None, **extra) -> str:
        t = int(ahora if ahora is not None else time.time())
        claims = {"sub": sub, "iss": emisor or self.emisor, "aud": audiencia or self.audiencia, "iat": t, "exp": t + vida_s,
                  "typ": typ, "jti": uuid.uuid4().hex, "realm_access": {"roles": list(roles)}, **extra}
        return jwt.encode(claims, self._llave, algorithm="RS256", headers={"kid": "prueba"})

    def verificador(self, **kw) -> VerificadorAprobador:
        return VerificadorAprobador(self._llave.public_key(), emisor=self.emisor, audiencia=self.audiencia, **kw)
