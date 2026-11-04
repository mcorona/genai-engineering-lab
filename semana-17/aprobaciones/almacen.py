"""Week 17, activity 6: where approval requests, run checkpoints and confirmed orders live (PostgreSQL, the lab database).

Tables, in their own schema (`hitl` by default; tests use a throwaway one):

* `solicitudes`: one approval request. What (`sku`, `cantidad`), why (`motivo`, the model's words), how much (`monto_mxn` = quantity x
  unit cost, computed here from the legacy table, never taken from the model), which evidence (the tool calls behind it), who asked
  (`solicitante`, the token subject), the level R-OC-APRUEBA requires, the deadline, and the decision.
* `checkpoints`: the paused run (its transcript and counters), taken ONCE on resume and deleted in the same transaction.
* `ordenes`: the side effect of an approval. Insert-only.
* `intentos`: every decision attempt, applied or refused, with who tried and why it was refused.

The database repeats the state machine as constraints and triggers, so an order cannot exist without an approval even if the Python
code is wrong or someone writes SQL by hand: an approved request needs an approver who is not the requester and has the level; a
decided request never changes again; nothing is deleted; an order needs an approved request, and only one.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from . import maquina as M


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class YaReanudada(Exception):
    """The checkpoint of this request was already taken (a run resumes once) or the request is still pending."""


_DDL = """
CREATE SCHEMA IF NOT EXISTS {s};

CREATE TABLE IF NOT EXISTS {s}.solicitudes (
    id               text PRIMARY KEY,
    corrida          text NOT NULL,
    tenant           text NOT NULL,
    tarea            text NOT NULL,
    solicitante      text NOT NULL,
    sku              text NOT NULL,
    cantidad         integer NOT NULL CHECK (cantidad > 0),
    motivo           text NOT NULL,
    evidencia        jsonb NOT NULL,
    costo_unitario   numeric(14, 4) NOT NULL CHECK (costo_unitario >= 0),
    monto_mxn        numeric(16, 2) NOT NULL CHECK (monto_mxn >= 0),
    nivel            text NOT NULL CHECK (nivel IN ('comprador', 'gerente', 'director')),
    estado           text NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'aprobada', 'rechazada', 'expirada')),
    creada_en        timestamptz NOT NULL,
    expira_en        timestamptz NOT NULL CHECK (expira_en > creada_en),
    decidida_en      timestamptz,
    aprobador        text,
    aprobador_nivel  text CHECK (aprobador_nivel IN ('comprador', 'gerente', 'director')),
    motivo_decision  text,
    traza            text CHECK (traza IS NULL OR traza ~ '^00-[0-9a-f]{{32}}-[0-9a-f]{{16}}-[0-9a-f]{{2}}$'),
    CHECK ((estado = 'pendiente') = (decidida_en IS NULL)),
    CHECK (estado <> 'aprobada' OR (aprobador IS NOT NULL AND aprobador <> solicitante AND decidida_en < expira_en
           AND array_position(ARRAY['comprador', 'gerente', 'director'], aprobador_nivel)
               >= array_position(ARRAY['comprador', 'gerente', 'director'], nivel))),
    CHECK (estado <> 'rechazada' OR (aprobador IS NOT NULL AND aprobador <> solicitante))
);

CREATE TABLE IF NOT EXISTS {s}.checkpoints (
    solicitud_id  text PRIMARY KEY REFERENCES {s}.solicitudes (id),
    creado_en     timestamptz NOT NULL,
    estado        jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS {s}.ordenes (
    id            text PRIMARY KEY,
    solicitud_id  text NOT NULL UNIQUE REFERENCES {s}.solicitudes (id),
    sku           text NOT NULL,
    cantidad      integer NOT NULL,
    monto_mxn     numeric(16, 2) NOT NULL,
    creada_en     timestamptz NOT NULL,
    estado        text NOT NULL DEFAULT 'CONFIRMADA' CHECK (estado = 'CONFIRMADA')
);

CREATE TABLE IF NOT EXISTS {s}.intentos (
    id            bigserial PRIMARY KEY,
    solicitud_id  text NOT NULL,
    sujeto        text,
    decision      text NOT NULL,
    aplicado      boolean NOT NULL,
    motivo        text NOT NULL,
    en            timestamptz NOT NULL
);

CREATE OR REPLACE FUNCTION {s}.solicitud_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'approval requests are never deleted';
    END IF;
    IF OLD.estado <> 'pendiente' THEN
        RAISE EXCEPTION 'request % is already %', OLD.id, OLD.estado;
    END IF;
    IF (NEW.id, NEW.corrida, NEW.tenant, NEW.tarea, NEW.solicitante, NEW.sku, NEW.cantidad, NEW.motivo, NEW.evidencia,
        NEW.costo_unitario, NEW.monto_mxn, NEW.nivel, NEW.creada_en, NEW.expira_en)
       IS DISTINCT FROM
       (OLD.id, OLD.corrida, OLD.tenant, OLD.tarea, OLD.solicitante, OLD.sku, OLD.cantidad, OLD.motivo, OLD.evidencia,
        OLD.costo_unitario, OLD.monto_mxn, OLD.nivel, OLD.creada_en, OLD.expira_en) THEN
        RAISE EXCEPTION 'what was asked for cannot change, only the decision';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION {s}.orden_con_aprobacion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'orders are insert-only';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM {s}.solicitudes s
                   WHERE s.id = NEW.solicitud_id AND s.estado = 'aprobada' AND s.sku = NEW.sku AND s.cantidad = NEW.cantidad
                     AND s.monto_mxn = NEW.monto_mxn) THEN
        RAISE EXCEPTION 'an order needs an approved request for the same item, quantity and amount';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS solicitud_inmutable ON {s}.solicitudes;
CREATE TRIGGER solicitud_inmutable BEFORE UPDATE OR DELETE ON {s}.solicitudes
    FOR EACH ROW EXECUTE FUNCTION {s}.solicitud_inmutable();
DROP TRIGGER IF EXISTS orden_con_aprobacion ON {s}.ordenes;
CREATE TRIGGER orden_con_aprobacion BEFORE INSERT OR UPDATE OR DELETE ON {s}.ordenes
    FOR EACH ROW EXECUTE FUNCTION {s}.orden_con_aprobacion();
"""


class Almacen:
    """`dsn` defaults to `PG_ADMIN_DSN` (the lab's admin: it creates the schema). `reloj` returns an aware UTC datetime."""

    def __init__(self, dsn: str | None = None, *, esquema: str = "hitl", reloj=ahora_utc):
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,40}", esquema):
            raise ValueError("schema name must be a plain lowercase identifier")
        self.dsn = dsn or os.environ["PG_ADMIN_DSN"]
        self.s, self.reloj = esquema, reloj

    def _con(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def crear(self) -> None:
        with self._con() as c:
            c.execute(_DDL.format(s=self.s))

    def borrar(self) -> None:
        """Drops the whole schema. Tests and throwaway schemas only."""
        with self._con() as c:
            c.execute(f"DROP SCHEMA IF EXISTS {self.s} CASCADE")

    # ---------- what is asked for ----------

    def costo_unitario(self, sku: str) -> float | None:
        with self._con() as c:
            fila = c.execute("SELECT art_cst FROM legado.artmst WHERE art_cd = %s", (sku,)).fetchone()
        return None if fila is None or fila["art_cst"] is None else float(fila["art_cst"])

    def crear_solicitud(self, *, corrida: str, tenant: str, tarea: str, solicitante: str, sku: str, cantidad: int, motivo: str,
                        evidencia: list, ttl_s: float, traza: str | None = None) -> dict:
        costo = self.costo_unitario(sku)
        if costo is None:
            raise ValueError("unknown SKU or no unit cost")
        monto = round(costo * cantidad, 2)
        ahora = self.reloj()
        fila = {"id": uuid.uuid4().hex[:12], "corrida": corrida, "tenant": tenant, "tarea": tarea, "solicitante": solicitante,
                "sku": sku, "cantidad": int(cantidad), "motivo": motivo[:2000], "evidencia": Jsonb(evidencia),
                "costo_unitario": costo, "monto_mxn": monto, "nivel": M.nivel_requerido(monto), "creada_en": ahora,
                "expira_en": ahora + timedelta(seconds=ttl_s), "traza": traza}
        with self._con() as c:
            c.execute(f"INSERT INTO {self.s}.solicitudes ({', '.join(fila)}) VALUES ({', '.join('%(' + k + ')s' for k in fila)})", fila)
        return self.obtener(fila["id"])

    def obtener(self, solicitud_id: str) -> dict | None:
        with self._con() as c:
            return c.execute(f"SELECT * FROM {self.s}.solicitudes WHERE id = %s", (solicitud_id,)).fetchone()

    # ---------- the paused run ----------

    def guardar_checkpoint(self, solicitud_id: str, estado: dict) -> None:
        with self._con() as c:
            c.execute(f"INSERT INTO {self.s}.checkpoints (solicitud_id, creado_en, estado) VALUES (%s, %s, %s)",
                      (solicitud_id, self.reloj(), Jsonb(estado)))

    def tomar_checkpoint(self, solicitud_id: str) -> tuple[dict, dict]:
        """The request (decided) and its checkpoint, which is deleted in the same transaction: a run resumes once, and the
        transcript (it holds tool results) does not outlive the resume."""
        with self._con() as c, c.transaction():
            s = c.execute(f"SELECT * FROM {self.s}.solicitudes WHERE id = %s FOR UPDATE", (solicitud_id,)).fetchone()
            if s is None or s["estado"] == "pendiente":
                raise YaReanudada("the request is not decided yet")
            cp = c.execute(f"DELETE FROM {self.s}.checkpoints WHERE solicitud_id = %s RETURNING estado", (solicitud_id,)).fetchone()
            if cp is None:
                raise YaReanudada("this run was already resumed")
        return s, cp["estado"]

    # ---------- the decision ----------

    def decidir(self, solicitud_id: str, identidad: M.Identidad | None, decision: str) -> tuple[M.Veredicto, dict | None]:
        """One decision attempt, in one transaction with the request locked: two approvers at once are serialized and the second
        one finds it decided. A late attempt expires the request. Every attempt is recorded in `intentos`."""
        ahora = self.reloj()
        with self._con() as c, c.transaction():
            s = c.execute(f"SELECT * FROM {self.s}.solicitudes WHERE id = %s FOR UPDATE", (solicitud_id,)).fetchone()
            v = M.evaluar(s, identidad, decision, ahora)
            if v.estado_nuevo == "expirada":
                c.execute(f"UPDATE {self.s}.solicitudes SET estado = 'expirada', decidida_en = %s, motivo_decision = 'vencida' "
                          f"WHERE id = %s", (ahora, solicitud_id))
            elif v.aplicado:
                c.execute(f"UPDATE {self.s}.solicitudes SET estado = %s, decidida_en = %s, aprobador = %s, aprobador_nivel = %s, "
                          f"motivo_decision = 'ok' WHERE id = %s",
                          (v.estado_nuevo, ahora, identidad.sub, M.nivel_de(identidad.roles), solicitud_id))
                if v.estado_nuevo == "aprobada":
                    c.execute(f"INSERT INTO {self.s}.ordenes (id, solicitud_id, sku, cantidad, monto_mxn, creada_en) "
                              f"VALUES (%s, %s, %s, %s, %s, %s)",
                              ("OC-" + uuid.uuid4().hex[:10], solicitud_id, s["sku"], s["cantidad"], s["monto_mxn"], ahora))
            c.execute(f"INSERT INTO {self.s}.intentos (solicitud_id, sujeto, decision, aplicado, motivo, en) "
                      f"VALUES (%s, %s, %s, %s, %s, %s)",
                      (solicitud_id, identidad.sub if identidad else None, decision[:20], v.aplicado, v.motivo, ahora))
            despues = c.execute(f"SELECT * FROM {self.s}.solicitudes WHERE id = %s", (solicitud_id,)).fetchone()
        return v, despues

    def anular(self, solicitud_id: str) -> None:
        """A request whose run cannot be resumed (the loop ended before pausing) expires at once: nothing can come of it."""
        with self._con() as c:
            c.execute(f"UPDATE {self.s}.solicitudes SET estado = 'expirada', decidida_en = %s, motivo_decision = 'sin_corrida' "
                      f"WHERE id = %s AND estado = 'pendiente'", (self.reloj(), solicitud_id))

    def expirar_vencidas(self) -> list[str]:
        """The sweep: every pending request past its deadline becomes `expirada`. Returns their ids."""
        ahora = self.reloj()
        with self._con() as c:
            filas = c.execute(f"UPDATE {self.s}.solicitudes SET estado = 'expirada', decidida_en = %s, motivo_decision = 'vencida' "
                              f"WHERE estado = 'pendiente' AND expira_en <= %s RETURNING id", (ahora, ahora)).fetchall()
        return [f["id"] for f in filas]

    # ---------- the audit ----------

    def orden_de(self, solicitud_id: str) -> dict | None:
        with self._con() as c:
            return c.execute(f"SELECT * FROM {self.s}.ordenes WHERE solicitud_id = %s", (solicitud_id,)).fetchone()

    def intentos(self, solicitud_id: str) -> list[dict]:
        with self._con() as c:
            return c.execute(f"SELECT sujeto, decision, aplicado, motivo FROM {self.s}.intentos WHERE solicitud_id = %s ORDER BY id",
                             (solicitud_id,)).fetchall()

    def auditoria(self) -> dict:
        """The security criteria, counted from the tables themselves."""
        niveles = "ARRAY['comprador', 'gerente', 'director']"
        with self._con() as c:
            malas = c.execute(f"""
                SELECT count(*) AS n FROM {self.s}.ordenes o LEFT JOIN {self.s}.solicitudes s ON s.id = o.solicitud_id
                WHERE s.id IS NULL OR s.estado <> 'aprobada' OR s.aprobador IS NULL OR s.aprobador = s.solicitante
                   OR array_position({niveles}, s.aprobador_nivel) < array_position({niveles}, s.nivel)
                   OR s.decidida_en >= s.expira_en""").fetchone()["n"]
            efectos = c.execute(f"""
                SELECT count(*) AS n FROM {self.s}.solicitudes s
                WHERE s.estado IN ('rechazada', 'expirada')
                  AND EXISTS (SELECT 1 FROM {self.s}.ordenes o WHERE o.solicitud_id = s.id)""").fetchone()["n"]
            por_estado = {f["estado"]: f["n"] for f in c.execute(
                f"SELECT estado, count(*) AS n FROM {self.s}.solicitudes GROUP BY 1").fetchall()}
            ordenes = c.execute(f"SELECT count(*) AS n FROM {self.s}.ordenes").fetchone()["n"]
            checkpoints = c.execute(f"SELECT count(*) AS n FROM {self.s}.checkpoints").fetchone()["n"]
        return {"ordenes": ordenes, "ordenes_sin_aprobacion": malas, "efectos_de_rechazos": efectos, "solicitudes": por_estado,
                "checkpoints_abiertos": checkpoints}
