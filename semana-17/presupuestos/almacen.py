"""Week 17, activity 4: the small store behind the session and per-day budgets (SQLite, standard library).

The task budget lives in the agent's memory. The session and tenant-day budgets outlive a task and are shared by tasks that run at
the same time, so they live here, and money is never read-then-written: before a model call the agent RESERVES the call's upper
cost in every scope it belongs to, inside one `BEGIN IMMEDIATE` transaction that re-checks each limit against what is spent plus
what other calls have reserved. After the call it SETTLES the reservation with the real cost (or releases it if the call failed).
Two tasks of one tenant can therefore never both be granted the last dollar.

A reservation whose process died never settles; it expires after `ttl_s` so that it cannot block a tenant forever.

Amounts are integers: nano-dollars (a Haiku input token costs 100 nano-dollars) and tokens. Reservations round up, settlements
round to nearest. The file holds counters and ids of sessions and tenants, never prompts, SQL or answers.
"""
from __future__ import annotations

import math
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .politica import Gasto, Limite

NANO = 10**9
_ESQUEMA = """
CREATE TABLE IF NOT EXISTS gasto (alcance TEXT NOT NULL, clave TEXT NOT NULL, dia TEXT NOT NULL,
    nano_usd INTEGER NOT NULL DEFAULT 0, tokens INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (alcance, clave, dia));
CREATE TABLE IF NOT EXISTS reservas (id INTEGER PRIMARY KEY AUTOINCREMENT, alcance TEXT NOT NULL, clave TEXT NOT NULL,
    dia TEXT NOT NULL, nano_usd INTEGER NOT NULL, tokens INTEGER NOT NULL, creada REAL NOT NULL, grupo TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS reservas_por_cuenta ON reservas (alcance, clave, dia);
"""

# A scope's account: (scope, key, day). A session has no day (""), a tenant's day is the UTC date.
Cuenta = tuple[str, str, str]


class AlmacenGasto:
    def __init__(self, ruta: str | Path, ttl_s: float = 600.0, reloj=time.time):
        self.ruta, self.ttl_s, self.reloj = str(ruta), ttl_s, reloj
        with self._conexion() as c:
            c.executescript(_ESQUEMA)

    @contextmanager
    def _conexion(self, inmediata: bool = False):
        c = sqlite3.connect(self.ruta, timeout=30, isolation_level=None)
        try:
            c.execute("PRAGMA busy_timeout = 30000")
            c.execute("PRAGMA journal_mode = WAL")
            if inmediata:
                c.execute("BEGIN IMMEDIATE")
            yield c
            if inmediata:
                c.execute("COMMIT")
        except BaseException:
            if inmediata:
                c.execute("ROLLBACK")
            raise
        finally:
            c.close()

    def _gastado(self, c, cuenta: Cuenta) -> tuple[int, int]:
        fila = c.execute("SELECT nano_usd, tokens FROM gasto WHERE alcance=? AND clave=? AND dia=?", cuenta).fetchone()
        reservas = c.execute("SELECT COALESCE(SUM(nano_usd),0), COALESCE(SUM(tokens),0) FROM reservas "
                             "WHERE alcance=? AND clave=? AND dia=? AND creada>=?", (*cuenta, self.reloj() - self.ttl_s)).fetchone()
        return (fila[0] if fila else 0) + reservas[0], (fila[1] if fila else 0) + reservas[1]

    def restante(self, cuentas: dict[str, Cuenta], limites: dict[str, Limite]) -> dict[str, Gasto]:
        """What each scope has left: its limit minus what is spent and what is reserved. Read-only."""
        salida = {}
        with self._conexion() as c:
            for alcance, cuenta in cuentas.items():
                usd, tok = self._gastado(c, cuenta)
                salida[alcance] = Gasto(limites[alcance].usd - usd / NANO, limites[alcance].tokens - tok)
        return salida

    def gastado(self, cuenta: Cuenta) -> Gasto:
        """Settled spend only (no reservations): what the scope has really cost."""
        with self._conexion() as c:
            fila = c.execute("SELECT nano_usd, tokens FROM gasto WHERE alcance=? AND clave=? AND dia=?", cuenta).fetchone()
        return Gasto((fila[0] if fila else 0) / NANO, fila[1] if fila else 0)

    def reservar(self, cuentas: dict[str, Cuenta], limites: dict[str, Limite], usd: float, tokens: int, grupo: str
                 ) -> tuple[bool, str | None, str | None]:
        """Reserves `usd` and `tokens` in every scope or in none. Returns (True, None, None), or (False, the scope that has
        no room, the dimension that does not fit: `usd` or `tokens`)."""
        nano = math.ceil(usd * NANO)
        with self._conexion(inmediata=True) as c:
            for alcance, cuenta in cuentas.items():
                gastado_usd, gastado_tok = self._gastado(c, cuenta)
                if gastado_usd + nano > math.floor(limites[alcance].usd * NANO):
                    return False, alcance, "usd"
                if gastado_tok + tokens > limites[alcance].tokens:
                    return False, alcance, "tokens"
            ahora = self.reloj()
            for alcance, (a, clave, dia) in cuentas.items():
                c.execute("INSERT INTO reservas (alcance, clave, dia, nano_usd, tokens, creada, grupo) VALUES (?,?,?,?,?,?,?)",
                          (a, clave, dia, nano, tokens, ahora, grupo))
        return True, None, None

    def liquidar(self, cuentas: dict[str, Cuenta], grupo: str, usd: float, tokens: int) -> None:
        """Replaces the reservation `grupo` by what the call really cost."""
        with self._conexion(inmediata=True) as c:
            c.execute("DELETE FROM reservas WHERE grupo=?", (grupo,))
            for cuenta in cuentas.values():
                c.execute("INSERT INTO gasto (alcance, clave, dia, nano_usd, tokens) VALUES (?,?,?,?,?) "
                          "ON CONFLICT(alcance, clave, dia) DO UPDATE SET nano_usd = nano_usd + excluded.nano_usd, "
                          "tokens = tokens + excluded.tokens", (*cuenta, round(usd * NANO), tokens))

    def liberar(self, grupo: str) -> None:
        """The call did not happen or failed: nothing was spent, the reservation goes away."""
        with self._conexion(inmediata=True) as c:
            c.execute("DELETE FROM reservas WHERE grupo=?", (grupo,))

    def reservado(self) -> int:
        """Reservations alive right now (all scopes); zero when no call is in flight."""
        with self._conexion() as c:
            return c.execute("SELECT COUNT(*) FROM reservas WHERE creada>=?", (self.reloj() - self.ttl_s,)).fetchone()[0]
