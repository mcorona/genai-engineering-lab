"""LegacyBridge v1: the approvers' passwords in the week 14 Keycloak, set once per machine and kept in `.secretos.env` (mode 600, ignored by
git, never printed). It imports week 17's approver roles first (`aprobaciones/realm_aprobadores.json`, existing resources skipped)."""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
S17 = AQUI.parents[1] / "semana-17"
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))
SECRETOS = AQUI / ".secretos.env"
APROBADORES = ("comprador", "gerente", "director")
NOMBRES = {"comprador": ("Compradora", "Categoria"), "gerente": ("Gerente", "Compras"), "director": ("Director", "Operaciones")}


def _leer() -> dict:
    if not SECRETOS.exists():
        return {}
    return dict(l.split("=", 1) for l in SECRETOS.read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))


def asegurar() -> dict[str, str]:
    """{approver: password}. Creates the passwords on the first call; later calls read them."""
    s = _leer()
    if all(f"KC_PWD_{u.upper()}" in s for u in APROBADORES):
        return {u: s[f"KC_PWD_{u.upper()}"] for u in APROBADORES}
    from aprobaciones import keycloak as K
    K.preparar()                                   # import the roles, users and client (and the `basic` scope)
    t = K._admin_token(K._secretos_kc())
    claves = {}
    for u in APROBADORES:
        _, usuarios = K._admin("GET", f"/users?username={u}&exact=true", t)
        uid = usuarios[0]["id"]
        claves[u] = secrets.token_urlsafe(18)
        K._admin("PUT", f"/users/{uid}/reset-password", t, {"type": "password", "value": claves[u], "temporary": False})
        K._admin("PUT", f"/users/{uid}", t, {"requiredActions": [], "firstName": NOMBRES[u][0], "lastName": NOMBRES[u][1],
                                              "email": f"{u}@legacybridge.invalid", "emailVerified": True})
    viejo = os.umask(0o077)
    try:
        with open(SECRETOS, "w", encoding="utf-8") as f:
            f.write("# LegacyBridge v1: approver passwords for the local Keycloak. Do not version.\n")
            for u, c in claves.items():
                f.write(f"KC_PWD_{u.upper()}={c}\n")
    finally:
        os.umask(viejo)
    os.chmod(SECRETOS, 0o600)
    return claves


if __name__ == "__main__":
    print(f"approver passwords ready for {len(asegurar())} users (in {SECRETOS.name}, not printed)")
    sys.exit(0)
