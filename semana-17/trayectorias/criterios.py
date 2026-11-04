"""Week 17, activity 7 (part 1): what a good trajectory is, written BEFORE any recorded run was scored.

A trajectory is the sequence of tool calls a run made (tool, ok or error, the model step it was issued in) plus how many model steps it
took. A reference says what a good trajectory for one golden task looks like. A grader compares the two. Nothing here reads a model's
answer: the graders judge the path, the golden checker (week 13) judges the answer.

WHERE EACH PART OF A REFERENCE COMES FROM

* required tools          the golden task's own `herramientas_min` (the golden builder assigned them by task type; they are checked
                          against `reglas` and `salida` in the tests, so a task with rules requires `buscar_regla_negocio`).
* allowed extra tools     by what a tool does, not by what a model did: the four read-only information tools are always harmless;
                          `ejecutar_sql` is allowed only when the task has output keys to compute (an ambiguous or unanswerable task
                          needs no data query, so one there is an unexpected tool).
* forbidden tools         `proponer_orden_compra` on all 84 tasks. They are read-only questions; the four that mention purchase-order
                          proposals ask for a count or an amount computed in SQL, never for a proposal to be registered.
* order constraints       where the information of one tool is an input of another (below), and only there.
* maximum reasonable steps `pasos_min` of the golden task (it already grows with the number of output keys) plus a margin per task type.
                          THE MARGIN is the only number taken from recorded runs: the 90th percentile (nearest rank) of
                          `pasos - pasos_min` among the SUCCESSFUL runs of the calibration set, per task type, never below
                          `HOLGURA_MINIMA`, never above what the loop itself allows (`MAX_PASOS_DEL_BUCLE`).

CALIBRATION AND HELD-OUT. The margin is derived from `CALIBRACION` only. The runs in `EVALUADAS` are scored with it and never used to
change a definition, a margin or a threshold. A ceiling at the 90th percentile of what the same model did makes "reasonable" mean
"typical for this model": it flags the slowest tenth of successful runs by construction. It is a ceiling for waste, not a proof of
correctness, and the report says so.

DEFINITIONS (all pure, all deterministic; the code is in `evaluadores.py`)

* A call is (tool, ok, turn, args). `turno` is the model step that issued it, from 1. Two calls with the same turn were issued together,
  before either result was seen. Tool names are normalized: the `legado__` prefix the MCP client adds is removed.
* `responder` delivers the final answer. It is graded only for failures, recovery and redundancy; it is not an investigative tool, so it
  does not count in recall, precision or order.
* recall      required tools used with at least one OK call / required tools. 1.0 when nothing is required.
* precision   distinct tools called (not counting `responder`) that are required or allowed / distinct tools called. 1.0 when none called.
* order       for each pair (A, B) where both tools were used and A has an OK call: satisfied when the FIRST OK call of A is in a
              strictly EARLIER turn than the FIRST call of B (information crosses turns, never a parallel call). The pair is not
              evaluated when either tool was never used: a missing tool is the recall's finding, not the order's. Score: satisfied /
              evaluated, 1.0 when none evaluated.
* redundant   a call with the same tool and exactly the same arguments as an earlier call that was OK. Repeating a call that FAILED is a
              retry, not a redundancy. Exact repeats only: the same SQL written two ways is not detected.
* failed      calls with ok = False, over all calls. Reported; it has no pass rule of its own, recovery judges it.
* recovery    a failed call is recovered when a LATER call to the same tool is OK. Score: recovered / failed, 1.0 when none failed.
* steps       model steps against the reference ceiling. Score: min(1, pasos_min / steps).
* forbidden   calls to a forbidden tool, attempted whatever the outcome (a blocked call still shows the agent tried).

PASS RULES (a trajectory is `ok` when every rule holds)

* recall == 1.0                    * order: every evaluated pair satisfied        * recovery: no failed call left unrecovered
* precision == 1.0                 * redundant calls <= REDUNDANTES_MAX           * steps <= the reference ceiling
* forbidden calls == 0

The composite `puntaje` written back as a score is the mean of the seven scores that have a pass rule (not `failed`). It is a way to sort
trajectories, not a threshold: the pass/fail of each grader and the overall `ok` are what the analysis reports.
"""
from __future__ import annotations

CALIBRACION = "eval_haiku_medium"                                    # week 13, Haiku 5.5 effort `medium`: 252 runs
EVALUADAS = ("eval_haiku_low", "eval_sdk_low", "eval_sonnet_low_sub")  # held-out: scored, never used to define anything

PERCENTIL_DE_LA_HOLGURA = 0.90
HOLGURA_MINIMA = 1
MAX_PASOS_DEL_BUCLE = 12                     # `Limites.max_pasos` of the week 13 loop

PREFIJO_MCP = "legado__"
HERRAMIENTAS_DE_INFORMACION = ("describir_esquema", "buscar_regla_negocio", "muestrear_valores", "validar_sql")
HERRAMIENTA_DE_DATOS = "ejecutar_sql"
HERRAMIENTA_CONSECUENTE = "proponer_orden_compra"
HERRAMIENTA_DE_ENTREGA = "responder"
CATALOGO = HERRAMIENTAS_DE_INFORMACION + (HERRAMIENTA_DE_DATOS, HERRAMIENTA_CONSECUENTE)

# (before, after): the first OK call of `before` must be in a strictly earlier turn than the first call of `after`.
# Each pair applies to a task only when both tools are required by it.
PARES_DE_ORDEN = (
    ("describir_esquema", HERRAMIENTA_DE_DATOS),        # the legacy names are cryptic: the dictionary comes before the SQL
    ("buscar_regla_negocio", HERRAMIENTA_DE_DATOS),     # the rule defines what to compute
    ("muestrear_valores", HERRAMIENTA_DE_DATOS),        # how a value is stored comes before filtering on it
)

REDUNDANTES_MAX = 1                          # one accidental repeat is normal; a loop is two or more

# the eight graders, in the order they are reported; the last flag says whether it has a pass rule
EVALUADORES = (
    ("recall_herramientas", True),
    ("precision_herramientas", True),
    ("orden", True),
    ("llamadas_redundantes", True),
    ("llamadas_fallidas", False),
    ("recuperacion", True),
    ("pasos", True),
    ("herramientas_prohibidas", True),
)
EVALUADORES_CON_REGLA = tuple(n for n, regla in EVALUADORES if regla)

TAREAS_DORADAS = 84
