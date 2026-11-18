"""Week 19, activity 6: the test users of the approval pool, one per group.

Groups (computo/tokens.py): analistas read; compradores propose and cannot approve; aprobadores-comprador,
aprobadores-gerente and aprobadores-director approve up to their level and cannot propose (Manuel's decision).

  python3 infra/usuarios.py --pool <id>            simulation (default): prints the plan. No AWS calls.
  python3 infra/usuarios.py --pool <id> --si       acts: creates the users, adds them to their groups.

Passwords are generated here, written only to semana-19/infra/.secretos.env (ignored by git, mode 0600, ADR 0013) and
never printed. An existing user is left as it is: its password is not reset. The pool id is not a secret, but the account
ID never appears in this file or in its output.
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

USUARIOS = [("analista-prueba", "analistas", "ANALISTA_PRUEBA_PASSWORD"),
            ("comprador-prueba", "compradores", "COMPRADOR_PRUEBA_PASSWORD"),
            ("aprobador-comprador-prueba", "aprobadores-comprador", "APROBADOR_COMPRADOR_PRUEBA_PASSWORD"),
            ("aprobador-prueba", "aprobadores-gerente", "APROBADOR_PRUEBA_PASSWORD"),
            ("aprobador-director-prueba", "aprobadores-director", "APROBADOR_DIRECTOR_PRUEBA_PASSWORD")]
# The file lives outside the repository when S19_SECRETOS points there (the lab's: ~/s19-secretos/usuarios-prueba.env).
SECRETOS = Path(os.environ.get("S19_SECRETOS") or Path(__file__).resolve().parent / ".secretos.env")


def generar_contrasena() -> str:
    # The pool requires lower, upper, digit and symbol; 18 random url-safe characters plus a fixed class suffix.
    return secrets.token_urlsafe(18) + "Aa1!"


def plan(pool: str) -> list[str]:
    return [f"crear {usuario} en el grupo {grupo} (pool {pool})" for usuario, grupo, _ in USUARIOS]


def _guardar(lineas: list[tuple[str, str]], ruta: Path) -> None:
    fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        for clave, valor in lineas:
            f.write(f"{clave}={valor}\n")


def crear(pool: str, cliente, si: bool, ruta: Path = SECRETOS) -> list[str]:
    """Returns one status line per user (no secret in it). Without `si` it only returns the plan."""
    if not si:
        return plan(pool)
    estados = []
    for usuario, grupo, clave in USUARIOS:
        try:
            cliente.admin_get_user(UserPoolId=pool, Username=usuario)
        except cliente.exceptions.UserNotFoundException:
            pass
        else:
            # An existing user keeps its password; its groups are set to exactly its group (a group that was removed
            # from the pool, such as the old `aprobadores`, is no longer listed for it).
            actuales = {g["GroupName"] for g in cliente.admin_list_groups_for_user(UserPoolId=pool, Username=usuario)["Groups"]}
            for sobrante in sorted(actuales - {grupo}):
                cliente.admin_remove_user_from_group(UserPoolId=pool, Username=usuario, GroupName=sobrante)
            if grupo not in actuales:
                cliente.admin_add_user_to_group(UserPoolId=pool, Username=usuario, GroupName=grupo)
            cambio = "" if actuales == {grupo} else f"; grupo ahora {grupo}"
            estados.append(f"{usuario}: ya existe, contraseña sin cambios{cambio}")
            continue
        contrasena = generar_contrasena()
        cliente.admin_create_user(UserPoolId=pool, Username=usuario, MessageAction="SUPPRESS",
                                  TemporaryPassword=contrasena)
        cliente.admin_set_user_password(UserPoolId=pool, Username=usuario, Password=contrasena, Permanent=True)
        cliente.admin_add_user_to_group(UserPoolId=pool, Username=usuario, GroupName=grupo)
        _guardar([(clave, contrasena)], ruta)
        estados.append(f"{usuario}: creado en {grupo}; contraseña guardada en {ruta.name}")
    return estados


def main(argv=None) -> int:
    import boto3

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pool", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--perfil", default=os.environ.get("S19_PERFIL_DESPLIEGUE", "semana19-despliegue"))
    parser.add_argument("--si", action="store_true")
    a = parser.parse_args(argv)
    if not a.si:
        for linea in crear(a.pool, None, False):
            print(linea)
        print("Simulación. Para crear los usuarios: añade --si, con el OK del plan.")
        return 0
    cliente = boto3.Session(profile_name=a.perfil, region_name=a.region).client("cognito-idp")
    for linea in crear(a.pool, cliente, True):
        print(linea)
    return 0


if __name__ == "__main__":
    sys.exit(main())
