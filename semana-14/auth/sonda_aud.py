"""A probe: which audience Keycloak issues depending on where `resource` goes (authorization, exchange, refresh). No API ($0)."""
from pkce import RECURSO, autorizar, canjear, claims, password, refrescar

def aud(t):
    return claims(t["access_token"])["aud"]

for nombre, en_aut, en_canje, scopes in [
    ("resource en autorización y canje", RECURSO, ..., ["legado:leer"]),
    ("resource solo en autorización", RECURSO, None, ["legado:leer"]),
    ("solo autorización + offline_access", RECURSO, None, ["legado:leer", "offline_access"]),
    ("ambos + offline_access", RECURSO, ..., ["legado:leer", "offline_access"]),
]:
    try:
        t = canjear(autorizar("analista", password("analista"), scopes, resource=en_aut), resource=en_canje)
        r = refrescar(t)
        print(f"{nombre:38s} scope={claims(t['access_token'])['scope']!s:38s} refresh={claims(t['refresh_token'])['typ']:8s} aud={aud(t)!s:28s} after refresh={aud(r)}")
    except Exception as e:  # noqa: BLE001
        print(f"{nombre:40s} error {e}")
