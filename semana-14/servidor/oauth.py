"""Week 14, activity 5: the MCP server as an OAuth 2.1 resource server with least privilege.

Pieces:
- `VerificadorJWT`: the signature via the issuer's JWKS (with caching and rotation by `kid`), a fixed RS256 algorithm (no `none` and
  no HS/RS confusion), exact `iss` and `aud`, `exp` with leeway, a mandatory `sub`, and access tokens only (`typ` Bearer).
- `Autorizador`: used by the HTTP boundary before the SDK. 401 if there is no token or it is invalid, 403 `insufficient_scope`
  if the operation needs scopes the token does not carry. Both with a `WWW-Authenticate` that includes `scope` and
  `resource_metadata` (the SDK does not add `scope`, a gap found in activity 1). The scope is decided from the validated body.
- `ContextoOAuth`: the week 13 Contexto built from the token. Tables, columns and tools come from the
  scopes (`auth/permisos_oauth.json`); the model's arguments never change the user or the permissions.
- `ConexionConRol` and `PoolConexiones`: each query runs on its own pool connection with `SET LOCAL ROLE` to the profile's
  PostgreSQL role (`auth/roles_bd.sql`). If the guard failed, the database would still deny it (defense in depth).
- `fabrica_oauth`: creates each request's tools from the token the SDK validated.

The token never leaves the server: it is not forwarded to the database or to another service, and it is not recorded in the traces.
"""
from __future__ import annotations

import json
import queue
import re
import threading
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import anyio
import jwt
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken

from .primitivas import PLANTILLAS, Herramientas  # primitivas adds semana-13 to sys.path

from herramientas import Contexto  # noqa: E402
from herramientas.herramientas import DICCIONARIO, TABLAS  # noqa: E402

PERMISOS = json.loads((Path(__file__).resolve().parents[1] / "auth" / "permisos_oauth.json").read_text(encoding="utf-8"))
SCOPE_BASE = PERMISOS["scope_base"]
SCOPES = ("legado:leer", "legado:ventas", "legado:proveedores", "legado:compras:proponer")
TABLA_SCOPE = {t: s for s, ts in PERMISOS["tablas_por_scope"].items() for t in ts}
_ESQUEMA = re.compile(r"^legado://esquema/([a-z0-9_]+)$")


# ---------- permissions per scope ----------

def scopes_de_tablas(tablas, columnas=()) -> set[str]:
    req = {TABLA_SCOPE[t] for t in tablas if t in TABLA_SCOPE}
    for c in columnas:
        req |= set(PERMISOS["columnas_restringidas"].get(c, []))
    return req


def scopes_requeridos(metodo: str | None, nombre: str | None) -> set[str]:
    """The scopes an operation needs, computed from the JSON-RPC body (never from the header)."""
    req = {SCOPE_BASE}
    if metodo == "tools/call" and nombre in PERMISOS["herramientas"]:
        req |= set(PERMISOS["herramientas"][nombre])
    elif metodo == "resources/read" and nombre and (m := _ESQUEMA.match(nombre)):
        req |= scopes_de_tablas([m.group(1)])
    elif metodo == "prompts/get" and nombre in PLANTILLAS:
        p = PLANTILLAS[nombre]
        req |= scopes_de_tablas(p.tablas, p.columnas)
        for h in p.herramientas:
            req |= set(PERMISOS["herramientas"].get(h, []))
    return req


def rol_bd(scopes) -> str | None:
    clave = " ".join(sorted(set(scopes) & {"legado:leer", "legado:ventas", "legado:proveedores"}))
    return PERMISOS["roles_bd"].get(clave)


@dataclass
class ContextoOAuth(Contexto):
    """A week 13 Contexto whose permissions come from the token's scopes."""
    scopes: frozenset = frozenset()
    cliente: str = ""

    @classmethod
    def de_token(cls, token: AccessToken, **kw) -> "ContextoOAuth":
        scopes = frozenset(token.scopes) & frozenset(SCOPES)
        roles = [r for s, r in PERMISOS["roles_internos"].items() if s in scopes]  # only for proponer_orden_compra
        return cls(usuario=token.subject or token.client_id, roles=roles, scopes=scopes, cliente=token.client_id, **kw)

    def tablas(self) -> list[str]:
        if SCOPE_BASE not in self.scopes:
            return []
        visibles = {t for s in self.scopes for t in PERMISOS["tablas_por_scope"].get(s, [])}
        return [t for t in TABLAS if t in visibles]

    def columna_permitida(self, tabla: str, columna: str) -> bool:
        req = PERMISOS["columnas_restringidas"].get(f"{tabla}.{columna}")
        return req is None or bool(set(req) & self.scopes)

    def restringidas(self) -> set[str]:
        return {k.split(".")[1] for k, req in PERMISOS["columnas_restringidas"].items() if not set(req) & self.scopes}

    def herramienta_visible(self, nombre: str) -> bool:
        return set(PERMISOS["herramientas"].get(nombre, [SCOPE_BASE])) <= self.scopes


# ---------- JWT validation ----------

class ErrorToken(Exception):
    pass


class VerificadorJWT:
    """The SDK's TokenVerifier. `verificar` is synchronous (it downloads the JWKS the first time); `verify_token` runs it in a thread."""

    def __init__(self, emisor: str, audiencia: str, jwks_uri: str, *, algoritmos=("RS256",), margen_s: int = 30,
                 cache_s: int = 300):
        self.emisor, self.audiencia, self.algoritmos, self.margen_s = emisor, audiencia, tuple(algoritmos), margen_s
        self.jwks = jwt.PyJWKClient(jwks_uri, cache_keys=True, lifespan=cache_s, timeout=10)

    def verificar(self, token: str) -> AccessToken:
        try:
            cabecera = jwt.get_unverified_header(token)
        except jwt.PyJWTError as e:
            raise ErrorToken(f"malformed: {e}") from None
        if cabecera.get("alg") not in self.algoritmos:          # rejects none, HS256 and anything else before anything
            raise ErrorToken(f"algorithm not allowed: {cabecera.get('alg')!r}")
        try:
            clave = self.jwks.get_signing_key_from_jwt(token).key   # unknown kid: refresh the JWKS once
            c = jwt.decode(token, clave, algorithms=list(self.algoritmos), audience=self.audiencia, issuer=self.emisor,
                           leeway=self.margen_s, options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        except jwt.PyJWTError as e:
            raise ErrorToken(f"{type(e).__name__}: {e}") from None
        if c.get("typ", "Bearer") != "Bearer":                   # an ID token or a refresh token is not an access token
            raise ErrorToken(f"token type not allowed: {c.get('typ')!r}")
        return AccessToken(token=token, client_id=c.get("azp") or c.get("client_id") or "",
                           scopes=str(c.get("scope", "")).split(), expires_at=int(c["exp"]), resource=self.audiencia,
                           subject=c["sub"], claims={k: c[k] for k in ("iss", "azp", "sid") if k in c})

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            return await anyio.to_thread.run_sync(self.verificar, token)
        except ErrorToken:
            return None


@dataclass
class Rechazo:
    estado: int
    www_authenticate: str
    cuerpo: dict
    motivo: str = ""          # only for the server's trace; never returned to the client


class Autorizador:
    """Decides 401/403 for POST /mcp before the SDK processes the request."""

    def __init__(self, verificador: VerificadorJWT, url_metadatos: str):
        self.verificador, self.url_metadatos = verificador, url_metadatos

    def _desafio(self, scopes: set[str], error: str | None = None, descripcion: str | None = None) -> str:
        partes = []
        if error:
            partes.append(f'error="{error}"')
        if descripcion:
            partes.append(f'error_description="{descripcion}"')
        partes.append(f'scope="{" ".join(sorted(scopes))}"')
        partes.append(f'resource_metadata="{self.url_metadatos}"')
        return "Bearer " + ", ".join(partes)

    async def evaluar(self, encabezados: dict[bytes, bytes], metodo: str | None, nombre) -> tuple[AccessToken | None, Rechazo | None]:
        req = scopes_requeridos(metodo, nombre if isinstance(nombre, str) else None)
        auth = encabezados.get(b"authorization", b"").decode("latin-1")
        if not auth:
            return None, Rechazo(401, self._desafio(req), {"error": "invalid_token",
                                                            "error_description": "Authentication required"}, "sin_token")
        esquema, _, token = auth.partition(" ")
        if esquema.lower() != "bearer" or not token.strip():
            return None, Rechazo(401, self._desafio(req, "invalid_request", "Bearer token required"),
                                 {"error": "invalid_request", "error_description": "Bearer token required"},
                                 "esquema_no_bearer")
        try:
            at = await anyio.to_thread.run_sync(self.verificador.verificar, token.strip())
        except ErrorToken as e:
            # the exact reason is not returned to the client (no help in forging tokens); it stays as "invalid_token"
            return None, Rechazo(401, self._desafio(req, "invalid_token", "The access token is invalid or expired"),
                                 {"error": "invalid_token", "error_description": "The access token is invalid or expired"},
                                 f"token_invalido: {e}"[:200])
        faltan = req - set(at.scopes)
        if faltan:
            return at, Rechazo(403, self._desafio(req, "insufficient_scope", "Missing scope: " + " ".join(sorted(faltan))),
                               {"error": "insufficient_scope", "error_description": "Missing scope: " + " ".join(sorted(faltan)),
                                "scope": " ".join(sorted(req))}, "faltan: " + " ".join(sorted(faltan)))
        return at, None


# ---------- database: a pool and a role per profile ----------

class PoolConexiones:
    """Dedicated connections per call (a psycopg connection is not shared between concurrent transactions)."""

    def __init__(self, dsn: str, tamano: int = 4, espera_s: float = 10.0):
        self.dsn, self.tamano, self.espera_s = dsn, tamano, espera_s
        self._libres: queue.Queue = queue.Queue()
        self._creadas = 0
        self._lock = threading.Lock()

    def tomar(self):
        import psycopg
        try:
            return self._libres.get_nowait()
        except queue.Empty:
            pass
        with self._lock:
            if self._creadas < self.tamano:
                self._creadas += 1
                crear = True
            else:
                crear = False
        if crear:
            try:
                conn = psycopg.connect(self.dsn, autocommit=True)
                conn.execute("SET search_path = legado")
                return conn
            except Exception:
                with self._lock:
                    self._creadas -= 1
                raise
        return self._libres.get(timeout=self.espera_s)

    def devolver(self, conn):
        import psycopg
        if conn.closed or conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
            try:
                conn.close()
            finally:
                with self._lock:
                    self._creadas -= 1
            return
        self._libres.put(conn)

    def cerrar(self):
        while True:
            try:
                self._libres.get_nowait().close()
            except queue.Empty:
                return


class ConexionConRol:
    """Behaves like the connection `Herramientas._correr` uses (transaction + execute), but each transaction takes a
    connection from the pool and starts with SET LOCAL ROLE to the profile's role. Without a role (no legado:leer) there is no database access."""

    def __init__(self, pool: PoolConexiones, rol: str | None):
        self.pool, self.rol = pool, rol
        self._local = threading.local()

    @contextmanager
    def transaction(self):
        from psycopg import sql
        from herramientas.herramientas import ErrorHerramienta
        if self.rol is None:
            raise ErrorHerramienta("permiso_denegado", "El token no da acceso a la base.", "Se requiere el scope legado:leer.")
        conn = self.pool.tomar()
        try:
            with conn.transaction():
                conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(self.rol)))
                self._local.conn = conn
                yield
        finally:
            self._local.conn = None
            self.pool.devolver(conn)

    def execute(self, *a, **k):
        return self._local.conn.execute(*a, **k)


def fabrica_oauth(pool: PoolConexiones | None, idioma: str = "es", reglas_extra: list | None = None):
    """The tools of the request in flight, from the token the SDK middleware validated.
    `reglas_extra` is only used by the security eval (poisoned rule documents, activity 6)."""
    propuestas: dict[str, list] = defaultdict(list)   # per subject: proposals are not mixed between users

    def fabrica() -> Herramientas:
        token = get_access_token()
        if token is None:   # does not happen behind the boundary and the SDK; if it does, no permissions
            token = AccessToken(token="", client_id="", scopes=[], subject="anonimo")
        rol = rol_bd(token.scopes) if SCOPE_BASE in token.scopes else None
        ctx = ContextoOAuth.de_token(token, conexion=ConexionConRol(pool, rol) if pool else None, idioma=idioma,
                                     propuestas=propuestas[token.subject or token.client_id],
                                     reglas_extra=list(reglas_extra or []))
        return Herramientas(ctx)
    return fabrica


def aplicar_roles_bd(admin_dsn: str) -> None:
    """Creates or updates the roles per profile (idempotent). Requires copilot_nlq to exist (herramientas/conexion.py)."""
    import psycopg
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute((Path(__file__).resolve().parents[1] / "auth" / "roles_bd.sql").read_text(encoding="utf-8"))


def columnas_visibles(ctx: Contexto, tabla: str) -> list[str]:
    return [c for c in DICCIONARIO[tabla]["columnas"] if ctx.columna_permitida(tabla, c)]
