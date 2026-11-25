"""Week 13, activity 2: tools with a contract over the legacy schema.

Five tools, the same for every pattern, so that the difference between patterns is only the orchestration:

- describir_esquema(tablas?)            the tables and columns visible to the user, with the data dictionary.
- buscar_regla_negocio(consulta, max)   business rules (semana-13/golden/reglas_negocio.json) by keyword or by id.
- muestrear_valores(tabla, columna)     the most frequent distinct values of a column, so that formats are not guessed.
- validar_sql(sql)                      the guard without executing: a single SELECT statement, no dangerous functions, only
                                        tables and columns allowed to the user; plus EXPLAIN on the database.
- ejecutar_sql(sql, max_filas)          validates and executes in a READ ONLY transaction that is always rolled back, with
                                        time and row limits.

Contract:
- Inputs validated with Pydantic (extra="forbid"): each tool's JSON Schema admits no extra properties, so
  the model cannot pass roles, a user or limits that the system did not give it.
- Output always JSON: {"ok": true, ...} or {"ok": false, "error": {"tipo", "mensaje", "sugerencia"}}. Never exceptions.
- Summarized outputs: rows truncated to max_filas, long texts trimmed and a character cap per response.
- Permissions: the user's roles come in the Contexto, which the system creates. Defense in depth: the guard and,
  underneath, the read-only database role with a READ ONLY transaction.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

import sqlglot
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlglot import exp

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
DICCIONARIO = json.loads((RAIZ / "semana-10" / "legado" / "diccionario.json").read_text(encoding="utf-8"))
# Week 13: a legacy free-text notes table (artnot), created by seguridad/artnot.sql; used to test injection in data.
DICCIONARIO.update(json.loads((AQUI / "diccionario_extra.json").read_text(encoding="utf-8")))
REGLAS = json.loads((RAIZ / "semana-13" / "golden" / "reglas_negocio.json").read_text(encoding="utf-8"))["reglas"]
PERMISOS = json.loads((AQUI / "permisos.json").read_text(encoding="utf-8"))
TABLAS = tuple(DICCIONARIO)  # prvmst, artmst, almmst, exidet, vtadia, ocpcab, artnot
MAX_CARACTERES = 6000

# Functions that write, read outside the schema or can lock the database. Compared by prefix, in lowercase.
FUNCIONES_PROHIBIDAS = ("lo_", "pg_", "dblink", "set_config", "current_setting", "nextval", "setval", "txid_",
                        "query_to_xml", "table_to_xml", "copy", "has_", "version", "inet_", "current_user", "session_user")
NODOS_PROHIBIDOS = tuple(getattr(exp, n) for n in ("Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter",
                                                     "AlterTable", "Command", "Into", "Copy", "Set", "Lock", "Grant",
                                                     "TruncateTable", "Transaction", "Commit", "Rollback")
                         if hasattr(exp, n))
RAICES_PERMITIDAS = tuple(getattr(exp, n) for n in ("Select", "Union", "Intersect", "Except", "SetOperation") if hasattr(exp, n))


# ---------- input contract ----------

class _Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DescribirEsquema(_Entrada):
    tablas: list[Literal[TABLAS]] | None = Field(  # type: ignore[valid-type]
        default=None, description="Tables to describe. Omit to list every table available to the user.")


class BuscarRegla(_Entrada):
    consulta: str = Field(min_length=1, max_length=200,
                          description="Words to search for (Spanish or English), or a rule id such as R-COB.")
    max_resultados: int = Field(default=3, ge=1, le=5)


class MuestrearValores(_Entrada):
    tabla: Literal[TABLAS]  # type: ignore[valid-type]
    columna: str = Field(min_length=1, max_length=40)
    limite: int = Field(default=10, ge=1, le=20)


class ValidarSql(_Entrada):
    sql: str = Field(min_length=1, max_length=4000, description="One PostgreSQL SELECT over the legacy tables.")


class ProponerOrdenCompra(_Entrada):
    sku: str = Field(pattern=r"^SKU-\d{4}$", description="Item code, e.g. SKU-0009.")
    cantidad: int = Field(ge=1, le=100000)
    motivo: str = Field(min_length=1, max_length=200)


class EjecutarSql(_Entrada):
    sql: str = Field(min_length=1, max_length=4000, description="One PostgreSQL SELECT over the legacy tables.")
    max_filas: int = Field(default=50, ge=1, le=200, description="Maximum rows to return; the total is always reported.")


ENTRADAS = {"describir_esquema": DescribirEsquema, "buscar_regla_negocio": BuscarRegla,
            "muestrear_valores": MuestrearValores, "validar_sql": ValidarSql, "ejecutar_sql": EjecutarSql,
            "proponer_orden_compra": ProponerOrdenCompra}

DESCRIPCIONES = {
    "describir_esquema": "Describe the legacy tables and columns available to the current user, with the data dictionary "
                         "(meaning of each cryptic name and value formats). Call it before writing SQL.",
    "buscar_regla_negocio": "Search the company's business rules (coverage, risk, reorder policy, purchase proposals and "
                            "approvals, surplus between distribution centers, ABC class...). Returns the exact definition "
                            "to compute. Use it whenever a question mentions a business term.",
    "muestrear_valores": "Return the most frequent distinct values of one column, to check how data is stored "
                         "(country codes, city names, category spelling, status codes) before filtering.",
    "validar_sql": "Check a SELECT without running it: single statement, read-only, allowed tables and columns, and "
                   "that the database can plan it. Returns structured errors with a suggestion.",
    "ejecutar_sql": "Validate and run one SELECT over the legacy tables in a read-only transaction, with time and row "
                    "limits. Returns columns, rows (up to max_filas) and the total row count.",
    "proponer_orden_compra": "Register a purchase order PROPOSAL for human approval. It never creates, approves or executes "
                             "an order and writes nothing to the database: a person with the right authorization level "
                             "must approve it. Only for users with the purchasing role.",
}


def definiciones() -> list[dict]:
    """Tool definitions in the Anthropic API format (name, description, input_schema)."""
    out = []
    for nombre, modelo in ENTRADAS.items():
        esquema = modelo.model_json_schema()
        esquema.pop("title", None)
        for p in esquema.get("properties", {}).values():
            p.pop("title", None)
        esquema["additionalProperties"] = False
        out.append({"name": nombre, "description": DESCRIPCIONES[nombre], "input_schema": esquema})
    return out


# ---------- context that the system creates ----------

@dataclass
class Contexto:
    """Injected by the system, never by the model."""
    usuario: str
    roles: list[str]
    conexion: object | None = None          # psycopg.Connection with a read-only role; None = no database
    idioma: Literal["es", "en"] = "es"
    timeout_ms: int = 5000
    llamadas: list[dict] = field(default_factory=list)  # call log (trace)
    propuestas: list[dict] = field(default_factory=list)  # registered proposals (never executed)
    reglas_extra: list[dict] = field(default_factory=list)  # security tests only: additional rule documents

    @classmethod
    def de_usuario(cls, usuario: str, **kw) -> "Contexto":
        return cls(usuario=usuario, roles=list(PERMISOS["usuarios"][usuario]), **kw)

    def tablas(self) -> list[str]:
        vistas = {t for r in self.roles for t in PERMISOS["tablas_por_rol"].get(r, [])}
        return [t for t in TABLAS if t in vistas]

    def columna_permitida(self, tabla: str, columna: str) -> bool:
        req = PERMISOS["columnas_restringidas"].get(f"{tabla}.{columna}")
        return req is None or bool(set(req) & set(self.roles))

    def restringidas(self) -> set[str]:
        """Columns (by name) that the user cannot read."""
        return {k.split(".")[1] for k, req in PERMISOS["columnas_restringidas"].items() if not set(req) & set(self.roles)}


class ErrorHerramienta(Exception):
    def __init__(self, tipo: str, mensaje: str, sugerencia: str = ""):
        super().__init__(mensaje)
        self.tipo, self.mensaje, self.sugerencia = tipo, mensaje, sugerencia


def _error(tipo, mensaje, sugerencia=""):
    return {"ok": False, "error": {"tipo": tipo, "mensaje": mensaje, "sugerencia": sugerencia}}


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _literal(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def _valor(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, str) and len(v) > 200:
        return v[:200] + "…"
    return v


# ---------- implementation ----------

class Herramientas:
    def __init__(self, ctx: Contexto):
        self.ctx = ctx

    def llamar(self, nombre: str, argumentos: dict) -> dict:
        """The single entry point: validates the arguments, executes and always returns a serializable dict."""
        inicio = time.perf_counter()
        if nombre not in ENTRADAS:
            res = _error("herramienta_desconocida", f"No existe la herramienta {nombre!r}.",
                         "Herramientas disponibles: " + ", ".join(ENTRADAS))
        else:
            try:
                entrada = ENTRADAS[nombre].model_validate(argumentos or {})
                res = getattr(self, "_" + nombre)(entrada)
            except ValidationError as e:
                detalle = "; ".join(f"{'.'.join(map(str, x['loc'])) or 'argumentos'}: {x['msg']}" for x in e.errors())
                res = _error("argumentos_invalidos", detalle, "Revisa el esquema de entrada de la herramienta; no admite campos extra.")
            except ErrorHerramienta as e:
                res = _error(e.tipo, e.mensaje, e.sugerencia)
            except Exception as e:  # noqa: BLE001  contract: never an exception toward the model
                res = _error("error_interno", f"{type(e).__name__}: {str(e).splitlines()[0][:300] if str(e) else ''}",
                             "Revisa la entrada; si persiste, reformula la consulta de forma más simple.")
        res = self._recortar(res)
        self.ctx.llamadas.append({"herramienta": nombre, "argumentos": argumentos, "ok": res["ok"],
                                  "error": res.get("error", {}).get("tipo"), "ms": round(1000 * (time.perf_counter() - inicio))})
        return res

    @staticmethod
    def _recortar(res: dict) -> dict:
        texto = json.dumps(res, ensure_ascii=False, default=str)
        while len(texto) > MAX_CARACTERES and res.get("filas"):
            res["filas"] = res["filas"][: max(1, len(res["filas"]) // 2)]
            res["filas_devueltas"] = len(res["filas"])
            res["truncado"] = True
            texto = json.dumps(res, ensure_ascii=False, default=str)
        return res

    # describir_esquema
    def _describir_esquema(self, e: DescribirEsquema) -> dict:
        visibles = self.ctx.tablas()
        pedidas = e.tablas or visibles
        no_disp = [t for t in pedidas if t not in visibles]
        if no_disp:
            raise ErrorHerramienta("tabla_no_disponible", f"Tablas no disponibles para este usuario: {', '.join(no_disp)}.",
                                   "Tablas disponibles: " + ", ".join(visibles))
        tablas = []
        for t in pedidas:
            d = DICCIONARIO[t]
            cols = [{"columna": c, "descripcion": desc} for c, desc in d["columnas"].items() if self.ctx.columna_permitida(t, c)]
            tablas.append({"tabla": t, "descripcion": d["descripcion"], "columnas": cols})
        return {"ok": True, "esquema": "legado", "tablas": tablas,
                "nota": "Escribe SQL de PostgreSQL sobre estas tablas, sin prefijo de esquema."}

    # buscar_regla_negocio
    def _buscar_regla_negocio(self, e: BuscarRegla) -> dict:
        idioma = self.ctx.idioma
        consulta = e.consulta.strip()
        por_id = [r for r in REGLAS + self.ctx.reglas_extra if r["id"].lower() == consulta.lower()]
        if por_id:
            elegidas = por_id
        else:
            tokens = {w for w in re.findall(r"[a-z0-9]+", _norm(consulta)) if len(w) > 2}
            puntajes = []
            for r in REGLAS + self.ctx.reglas_extra:
                nombre = set(re.findall(r"[a-z0-9]+", _norm(r["nombre"] + " " + r["nombre_en"] + " " + r["id"])))
                cuerpo = set(re.findall(r"[a-z0-9]+", _norm(r["es"] + " " + r["en"])))
                p = 2 * len(tokens & nombre) + len(tokens & cuerpo)
                if p:
                    puntajes.append((p, r))
            puntajes.sort(key=lambda x: -x[0])
            elegidas = [r for _, r in puntajes[: e.max_resultados]]
        if not elegidas:
            return {"ok": True, "reglas": [], "sugerencia": "Sin coincidencias. Prueba con otro término o con un id: "
                                                            + ", ".join(r["id"] for r in REGLAS)}
        return {"ok": True, "reglas": [{"id": r["id"], "nombre": r["nombre" if idioma == "es" else "nombre_en"], "definicion": r[idioma], "fuente": r["fuente"]}
                                       for r in elegidas]}

    # muestrear_valores
    def _muestrear_valores(self, e: MuestrearValores) -> dict:
        if e.tabla not in self.ctx.tablas():
            raise ErrorHerramienta("permiso_denegado", f"El usuario no puede leer la tabla {e.tabla}.",
                                   "Tablas disponibles: " + ", ".join(self.ctx.tablas()))
        if e.columna not in DICCIONARIO[e.tabla]["columnas"]:
            raise ErrorHerramienta("columna_desconocida", f"La tabla {e.tabla} no tiene la columna {e.columna}.",
                                   "Columnas: " + ", ".join(c for c in DICCIONARIO[e.tabla]["columnas"] if self.ctx.columna_permitida(e.tabla, c)))
        if not self.ctx.columna_permitida(e.tabla, e.columna):
            raise ErrorHerramienta("permiso_denegado", f"El usuario no puede leer {e.tabla}.{e.columna}.",
                                   "Pide la información a alguien con el rol requerido o reformula sin esa columna.")
        sql = f"SELECT {e.columna} AS valor, COUNT(*) AS n FROM {e.tabla} GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {e.limite}"
        columnas, filas = self._correr(sql)
        distintos = self._correr(f"SELECT COUNT(DISTINCT {e.columna}) FROM {e.tabla}")[1][0][0]
        return {"ok": True, "tabla": e.tabla, "columna": e.columna, "valores_distintos": distintos,
                "valores": [{"valor": _valor(v), "filas": n} for v, n in filas]}

    # proponer_orden_compra
    def _proponer_orden_compra(self, e: ProponerOrdenCompra) -> dict:
        permitidos = PERMISOS.get("herramientas_por_rol", {}).get("proponer_orden_compra", [])
        if not set(permitidos) & set(self.ctx.roles):
            raise ErrorHerramienta("permiso_denegado", "El usuario no puede registrar propuestas de orden de compra.",
                                   "Solo el rol de compras puede proponer órdenes.")
        if self.ctx.conexion is not None and not self._correr("SELECT 1 FROM artmst WHERE art_cd = %s" % _literal(e.sku))[1]:
            raise ErrorHerramienta("sku_desconocido", f"No existe el artículo {e.sku}.", "Revisa el código con ejecutar_sql.")
        propuesta = {"id": f"PROP-{len(self.ctx.propuestas) + 1:04d}", "sku": e.sku, "cantidad": e.cantidad, "motivo": e.motivo,
                     "estado": "PENDING_APPROVAL", "ejecutada": False}
        self.ctx.propuestas.append(propuesta)
        return {"ok": True, "propuesta": propuesta,
                "nota": "Solo se registró la propuesta. No se creó ni aprobó ninguna orden y no se escribió nada en la base; "
                        "una persona con el nivel de autorización del monto debe aprobarla."}

    # validar_sql
    def _validar_sql(self, e: ValidarSql) -> dict:
        normalizado = self._guard(e.sql)
        if self.ctx.conexion is not None:
            self._correr("EXPLAIN " + e.sql, explicar=True)
        return {"ok": True, "valido": True, "sql_normalizado": normalizado}

    # ejecutar_sql
    def _ejecutar_sql(self, e: EjecutarSql) -> dict:
        normalizado = self._guard(e.sql)
        if self.ctx.conexion is None:
            raise ErrorHerramienta("sin_base", "No hay conexión a la base en este contexto.", "")
        columnas, filas = self._correr(e.sql)
        res = {"ok": True, "columnas": columnas, "total_filas": len(filas), "filas_devueltas": min(len(filas), e.max_filas),
               "truncado": len(filas) > e.max_filas, "filas": [[_valor(v) for v in f] for f in filas[: e.max_filas]],
               "sql_normalizado": normalizado}
        if not filas:
            res["nota"] = ("0 filas. Si filtraste por un texto o código, revisa cómo se guarda con muestrear_valores; "
                           "si aplicaste una regla, confirma su definición con buscar_regla_negocio.")
        return res

    # ---------- guard ----------
    def _guard(self, sql: str) -> str:
        try:
            sentencias = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
        except sqlglot.errors.SqlglotError as err:  # ParseError, TokenError and the other parser errors
            raise ErrorHerramienta("sql_invalido", f"No se pudo interpretar el SQL: {str(err).splitlines()[0]}",
                                   "Escribe una sola sentencia SELECT de PostgreSQL.")
        if len(sentencias) != 1:
            raise ErrorHerramienta("multiples_sentencias", f"Se recibieron {len(sentencias)} sentencias.",
                                   "Envía una sola sentencia SELECT, sin punto y coma intermedio.")
        raiz = sentencias[0]
        prohibido = next((n for n in raiz.walk() if isinstance(n, NODOS_PROHIBIDOS)), None)
        if prohibido is not None or not isinstance(raiz, RAICES_PERMITIDAS):
            tipo = type(prohibido or raiz).__name__.upper()
            raise ErrorHerramienta("escritura_bloqueada", f"Solo se permiten consultas SELECT de lectura (se encontró {tipo}).",
                                   "Esta herramienta es de solo lectura; las acciones con efectos no se ejecutan desde aquí.")
        for f in raiz.find_all(exp.Func):
            nombre = (f.name if isinstance(f, exp.Anonymous) else f.sql_name()).lower()
            if nombre.startswith(FUNCIONES_PROHIBIDAS):
                raise ErrorHerramienta("funcion_prohibida", f"La función {nombre} no está permitida.",
                                       "Usa solo funciones de consulta (agregados, fechas, texto, matemáticas).")
        ctes = {c.alias_or_name.lower() for c in raiz.find_all(exp.CTE)}
        visibles = self.ctx.tablas()
        usadas = []
        for t in raiz.find_all(exp.Table):
            nombre, esquema = (t.name or "").lower(), (t.db or "").lower()
            if not nombre or (nombre in ctes and not esquema):
                continue
            if esquema and esquema != "legado":
                raise ErrorHerramienta("permiso_denegado", f"Solo se puede consultar el esquema legado (se pidió {esquema}.{nombre}).",
                                       "Tablas disponibles: " + ", ".join(visibles))
            if nombre not in TABLAS:
                raise ErrorHerramienta("tabla_no_disponible", f"La tabla {nombre} no existe o no está disponible.",
                                       "Tablas disponibles: " + ", ".join(visibles))
            if nombre not in visibles:
                raise ErrorHerramienta("permiso_denegado", f"El usuario no puede leer la tabla {nombre}.",
                                       "Tablas disponibles: " + ", ".join(visibles))
            usadas.append(nombre)
        restringidas = self.ctx.restringidas()
        for c in raiz.find_all(exp.Column):
            if c.name.lower() in restringidas:
                raise ErrorHerramienta("permiso_denegado", f"El usuario no puede leer la columna {c.name}.",
                                       "Reformula la consulta sin esa columna.")
        if restringidas and any(c for t in usadas for c in DICCIONARIO[t]["columnas"] if c in restringidas):
            for s in raiz.find_all(exp.Star):
                if not isinstance(s.parent, exp.Count):
                    raise ErrorHerramienta("permiso_denegado", "SELECT * incluiría columnas que el usuario no puede leer.",
                                           "Enumera las columnas que necesitas.")
        return raiz.sql(dialect="postgres")

    # ---------- database ----------
    def _correr(self, sql: str, explicar: bool = False):
        import psycopg

        conn = self.ctx.conexion
        if conn is None:
            raise ErrorHerramienta("sin_base", "No hay conexión a la base en este contexto.", "")
        try:
            with conn.transaction():
                conn.execute("SET TRANSACTION READ ONLY")
                conn.execute(f"SET LOCAL statement_timeout = {int(self.ctx.timeout_ms)}")
                conn.execute("SET LOCAL search_path = legado")
                cur = conn.execute(sql)
                columnas = [d.name for d in cur.description] if cur.description else []
                filas = cur.fetchall() if cur.description else []
                raise psycopg.Rollback()
        except psycopg.errors.QueryCanceled:
            raise ErrorHerramienta("tiempo_agotado", f"La consulta excedió {self.ctx.timeout_ms} ms.",
                                   "Filtra antes de agrupar, evita productos cartesianos y agrega condiciones de unión.")
        except psycopg.errors.ReadOnlySqlTransaction:
            raise ErrorHerramienta("escritura_bloqueada", "La base rechazó una escritura: la sesión es de solo lectura.", "")
        except psycopg.errors.InsufficientPrivilege as err:
            raise ErrorHerramienta("permiso_denegado", f"La base negó el acceso: {str(err).splitlines()[0]}", "")
        except psycopg.Error as err:
            estado = getattr(err, "sqlstate", "") or ""
            pistas = {"42703": "Columna inexistente: revisa los nombres con describir_esquema.",
                      "42P01": "Tabla inexistente: tablas disponibles: " + ", ".join(self.ctx.tablas()),
                      "42883": "Función u operador inexistente para esos tipos: revisa los tipos de las columnas.",
                      "22P02": "Formato de valor inválido: revisa el tipo de la columna o usa muestrear_valores.",
                      "42803": "Columna fuera del GROUP BY o de una función de agregado.",
                      "22012": "División entre cero: protege el divisor con NULLIF."}
            raise ErrorHerramienta("error_sql", f"[{estado}] {str(err).splitlines()[0]}", pistas.get(estado, "Revisa la sintaxis y los nombres."))
        return columnas, filas
