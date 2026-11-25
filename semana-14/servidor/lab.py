"""Lab utilities shared by the tests and the security eval (activity 6).

- `ServidorHTTP`: a real uvicorn on 127.0.0.1, in a thread, on a free port.
- `EmisorDePrueba`: its own RSA key, a JWKS served on loopback and tokens signed with the claims Keycloak issues. It serves
  to run the eval without Keycloak; with Keycloak, its real tokens are used (auth/pkce.py).
"""
from __future__ import annotations

import http.server
import json
import socket
import threading
import time

from .http import HOST, RUTA, Trazas, crear_app

PERFILES = {"analista": ["legado:leer", "legado:ventas", "legado:proveedores", "legado:compras:proponer"],
            "almacenista": ["legado:leer"],
            "vendedor": ["legado:leer", "legado:ventas"]}


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


class ServidorHTTP:
    """A real uvicorn on 127.0.0.1. `verificador` can be a factory `f(recurso)` (the URI depends on the port)."""

    def __init__(self, servidor_mcp, puerto: int | None = None, **kw):
        import uvicorn

        self.puerto = puerto or puerto_libre()
        self.trazas = kw.pop("trazas", None) or Trazas()
        self.recurso = kw.get("recurso") or f"http://{HOST}:{self.puerto}{RUTA}"
        v = kw.get("verificador")
        if callable(v) and not hasattr(v, "verify_token"):
            kw["verificador"] = v(self.recurso)
        self.app = crear_app(servidor_mcp, self.puerto, trazas=self.trazas, **kw)
        self.server = uvicorn.Server(uvicorn.Config(self.app, host=HOST, port=self.puerto, log_level="error", lifespan="on"))
        self.hilo = threading.Thread(target=self.server.run, daemon=True)
        self.hilo.start()
        fin = time.time() + 10
        while not self.server.started:
            if time.time() > fin:
                raise RuntimeError("uvicorn did not start")
            time.sleep(0.02)
        self.url = f"http://{HOST}:{self.puerto}{RUTA}"

    def direcciones(self):
        return [sock.getsockname() for srv in self.server.servers for sock in srv.sockets]

    def cerrar(self):
        self.server.should_exit = True
        self.hilo.join(timeout=10)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.cerrar()


class EmisorDePrueba:
    """A minimal lab OAuth issuer: signs RS256 with its own key and publishes the JWKS on loopback."""

    def __init__(self, emisor: str = "http://127.0.0.1:8180/realms/legacybridge", kid: str = "lab-1"):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        self.emisor, self.kid = emisor, kid
        self.llave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.llave.public_key()))
        datos = json.dumps({"keys": [{**jwk, "kid": kid, "alg": "RS256", "use": "sig"}]}).encode()

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)

            def log_message(self, *a):
                pass
        self._srv = http.server.ThreadingHTTPServer((HOST, 0), H)
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        self.jwks_uri = f"http://{HOST}:{self._srv.server_address[1]}/certs"

    def token(self, recurso: str, usuario: str = "analista", scopes=None, llave=None, kid=None, alg="RS256", **cambios) -> str:
        import jwt
        ahora = int(time.time())
        claims = {"iss": self.emisor, "aud": recurso, "sub": f"sub-{usuario}", "azp": "legacybridge-agente", "typ": "Bearer",
                  "scope": " ".join(PERFILES.get(usuario, []) if scopes is None else scopes), "iat": ahora, "exp": ahora + 300}
        claims.update(cambios)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, llave or self.llave, algorithm=alg, headers={"kid": kid or self.kid})

    def cerrar(self):
        self._srv.shutdown()
