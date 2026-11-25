"""Week 20, activity 1: the corrected run of the 20 tasks, the regression gate (Manuel's OK of 2026-11-23).

    .venv/bin/python semana-20/linea_base/corrida.py                         simulation: the plan and the caps, no AWS
    S19_PERFIL=manuel-admin .venv/bin/python semana-20/linea_base/corrida.py --si     the run (Manuel runs it)
    .venv/bin/python semana-20/linea_base/corrida.py --informe               the detail file, offline

The same run as week 19's `eval/eval_aws.py` (the warm-up, then the 10 + 10 CI golden tasks one at a time, through
the public API with real Cognito tokens, the week 13 verifier, the week 17 graders and the week 10 rule), with three
differences, from `resultados/linea_base.md` section 3:
- the deployed agent must run the per-task ceiling (`PRESUPUESTO_TAREA=techo_semana20`, 0.12 USD and 100,000 tokens),
  so the budget cuts no task. The run checks the agent's environment and sends nothing otherwise;
- its own caps, over this run only (and any rerun of it, discarded ones included), not week 19's runs;
- no `cachePoint` (week 20 measures caching alone, in activity 3).

Its output goes to `resultados/corrida_corregida/`, and the detail to `resultados/corrida_corregida_detalle.jsonl`.

Week 20, activity 3 reuses this run as it is (`cache/corrida.py`): `Corrida` holds what changes from one run to the
next (its folder, caps, expected cost, the agent environment it requires, extra detail columns, the agent files whose
deployed code must be the repository's), and `main` takes one.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Callable

S20 = Path(__file__).resolve().parents[1]
RAIZ = S20.parent
S19 = RAIZ / "semana-19"
SALIDA = S20 / "resultados" / "corrida_corregida"
DETALLE = S20 / "resultados" / "corrida_corregida_detalle.jsonl"
PRESUPUESTO = "techo_semana20"
# Hard caps over the warm-up and the 20 tasks of this run. 2.50 USD is Manuel's OK; the tokens follow from 22 tasks at
# the ceiling's 100,000. The expected spend is about 0.90 USD (resultados/linea_base.md, section 3).
TOPE_USD = 2.50
TOPE_TOKENS = 2_200_000
COSTO_ESPERADO_TAREA = 0.045   # USD: week 19's median 0.037, plus the steps the cut tasks still needed
# The agent package (semana-19/infra/paquete_agente.py, CODIGO) puts semana-19/agente under app/agente in the zip.
PREFIJO_PAQUETE = "app/"


class Corrida:
    """One run of the 20 tasks: where it writes, its caps over its own files, and what the agent must be running.
    A plain class, not a dataclass: this module is loaded from its file without a sys.modules entry."""

    def __init__(self, *, salida: Path, detalle: Path, tope_usd: float, tope_tokens: int, costo_esperado_tarea: float,
                 exigir: dict | None = None,
                 columnas_detalle: Callable[[dict, list[dict]], list[dict]] | None = None,
                 codigo_al_dia: tuple[str, ...] = ()):
        self.salida, self.detalle = salida, detalle
        self.tope_usd, self.tope_tokens, self.costo_esperado_tarea = tope_usd, tope_tokens, costo_esperado_tarea
        self.exigir = dict(exigir or {"PRESUPUESTO_TAREA": PRESUPUESTO})
        self.columnas_detalle = columnas_detalle   # (raw run, detail lines) -> lines with the run's own columns
        self.codigo_al_dia = tuple(codigo_al_dia)   # files under semana-19/ the deployed package must match; () = no check


CORREGIDA = Corrida(salida=SALIDA, detalle=DETALLE, tope_usd=TOPE_USD, tope_tokens=TOPE_TOKENS,
                    costo_esperado_tarea=COSTO_ESPERADO_TAREA)


def _eval_aws():
    """Week 19's eval module, with the agent's budget set to the ceiling, so the per-task reservation of the script's
    cap (comparar.limite_de_tarea) is the same limit the deployed agent enforces."""
    os.environ["PRESUPUESTO_TAREA"] = PRESUPUESTO
    for ruta in (S19, RAIZ / "semana-17"):
        if str(ruta) not in sys.path:
            sys.path.insert(0, str(ruta))
    spec = importlib.util.spec_from_file_location("eval_aws_s19", S19 / "eval" / "eval_aws.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def tope(E, carpeta: Path = SALIDA, corrida: Corrida = CORREGIDA):
    """This run's cap minus what its earlier attempts spent (their raw files, discarded ones included)."""
    t = E.C.Tope(usd=corrida.tope_usd, tokens=corrida.tope_tokens)
    for archivo in sorted(carpeta.glob("crudo_eval*.json")):
        g = json.loads(archivo.read_text(encoding="utf-8"))["gasto"]
        t.sumar(g["usd"], g["tokens"])
    return t


def plan(E, tareas: list[dict], calentamiento: list[dict], corrida: Corrida = CORREGIDA) -> dict:
    t = tope(E, corrida.salida, corrida)
    lim = E.C.limite_de_tarea()
    return {"tareas": [x["id"] for x in tareas], "calentamiento": [x["id"] for x in calentamiento],
            "presupuesto_del_agente": {"valor": PRESUPUESTO, "usd": lim.usd, "tokens": lim.tokens},
            "entorno_exigido": dict(corrida.exigir),
            "tope": {"usd": corrida.tope_usd, "tokens": corrida.tope_tokens},
            "gastado_antes": {"usd": round(t.gastado_usd, 6), "tokens": t.gastado_tokens},
            "esperado_usd_modelo": round(corrida.costo_esperado_tarea * (len(tareas) + len(calentamiento)), 2)}


def exigir_presupuesto(variables: dict) -> None:
    valor = variables.get("PRESUPUESTO_TAREA", "semana17")
    if valor != PRESUPUESTO:
        raise SystemExit(f"the deployed agent uses PRESUPUESTO_TAREA={valor}: deploy computo with "
                         f"PRESUPUESTO_TAREA={PRESUPUESTO}; no task is sent")


def exigir_entorno(variables: dict, corrida: Corrida = CORREGIDA) -> None:
    """Nothing is sent unless the deployed agent runs every value the run requires."""
    exigir_presupuesto(variables)
    for clave, valor in corrida.exigir.items():
        if variables.get(clave) != valor:
            raise SystemExit(f"the deployed agent has {clave}={variables.get(clave)}: deploy computo with "
                             f"{clave}={valor}; no task is sent")


def codigo_desplegado_al_dia(zip_bytes: bytes, raiz: Path, archivos: tuple[str, ...]) -> list[str]:
    """The files (relative to semana-19/) whose bytes in the deployed agent package differ from the repository's,
    or that the package lacks."""
    with zipfile.ZipFile(BytesIO(zip_bytes)) as z:
        presentes = set(z.namelist())
        return [a for a in archivos
                if PREFIJO_PAQUETE + a not in presentes or z.read(PREFIJO_PAQUETE + a) != (raiz / a).read_bytes()]


def exigir_codigo(zip_bytes: bytes, corrida: Corrida = CORREGIDA, raiz: Path = S19) -> None:
    """Nothing is sent unless the deployed agent runs the repository's code for the files the run depends on."""
    if not corrida.codigo_al_dia:
        return
    distintos = codigo_desplegado_al_dia(zip_bytes, raiz, corrida.codigo_al_dia)
    if distintos:
        raise SystemExit(f"the deployed agent code differs from the repository in {', '.join(distintos)}: rebuild with "
                         "semana-19/infra/paquete_agente.py and deploy computo; no task is sent")


def escribir_detalle(E, datos: dict, corrida: Corrida = CORREGIDA) -> Path:
    lineas = E.detalle(datos)
    if corrida.columnas_detalle is None:
        return E.escribir_detalle(lineas, corrida.detalle)
    for l in lineas:   # the base columns keep week 19's schema; the run's own columns are added after the check
        errores = E.validar_detalle(l)
        if errores:
            raise ValueError(f"line outside the schema: {l['id']}: {errores}")
    extendidas = corrida.columnas_detalle(datos, lineas)
    corrida.detalle.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in extendidas), encoding="utf-8")
    return corrida.detalle


def descartar_previa(carpeta: Path = SALIDA) -> Path | None:
    actual = carpeta / "crudo_eval.json"
    if not actual.exists():
        return None
    destino = carpeta / f"crudo_eval_descartada_{1 + len(list(carpeta.glob('crudo_eval_descartada_*.json')))}.json"
    actual.rename(destino)
    return destino


def main(argv=None, corrida: Corrida = CORREGIDA) -> int:  # pragma: no cover - the CLI around the tested functions
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--si", "--yes", action="store_true", help="act (by default it only simulates)")
    ap.add_argument("--informe", "--report", action="store_true", help="writes the detail from the raw file, without AWS")
    a = ap.parse_args(argv)
    E = _eval_aws()
    tareas, calentamiento = E.tareas_ci(), E.tareas_de_calentamiento()
    if a.informe:
        datos = json.loads((corrida.salida / "crudo_eval.json").read_text(encoding="utf-8"))
        print(escribir_detalle(E, datos, corrida))
        print(json.dumps({k: datos[k] for k in ("resumen", "gasto", "acceso")}, ensure_ascii=False, indent=2))
        return 0
    if not a.si:
        print(json.dumps(plan(E, tareas, calentamiento, corrida), ensure_ascii=False, indent=2))
        print("Simulation: no AWS calls were made. Add --si (--yes) to act.")
        return 0
    aws = E.AwsEval(os.environ.get("S19_PERFIL", "manuel-admin"))
    if aws.camino_desplegado != "directo":
        raise SystemExit(f"the deployed agent uses {aws.camino_desplegado}; the run goes through the direct path")
    exigir_entorno(aws.lam.get_function_configuration(FunctionName=aws.computo["ArnAgente"])
                   ["Environment"]["Variables"], corrida)
    if corrida.codigo_al_dia:   # GetFunction is free and read-only; Code.Location is a presigned HTTPS URL to the zip
        ubicacion = aws.lam.get_function(FunctionName=aws.computo["ArnAgente"])["Code"]["Location"]
        if not ubicacion.startswith("https://"):
            raise SystemExit("GetFunction did not return an HTTPS URL for the agent code; no task is sent")
        with urllib.request.urlopen(ubicacion, timeout=120) as r:  # noqa: S310 - https only, checked above
            exigir_codigo(r.read(), corrida)
    todas = tareas + calentamiento
    esperados = aws.cargador_invoca({"modo": "esperados", "consultas": E.consultas_esperadas(todas)})["esperados"]
    tareas, calentamiento = E.con_esperados(tareas, esperados), E.con_esperados(calentamiento, esperados)
    token = aws.token("analista")
    acceso = E.controles_de_acceso(aws.http, token)
    if not all(c["ok"] for c in acceso):
        print(json.dumps(acceso, ensure_ascii=False, indent=2))
        raise SystemExit("the access checks did not return 401 and 403: no task is sent")
    previa = descartar_previa(corrida.salida)
    if previa:
        print(f"previous run kept as {previa.name}; its spend still counts toward the cap")
    t = tope(E, corrida.salida, corrida)
    medir = lambda x: E.C.medir_api(x, "directo", token=token, http=aws.http, spans_entre=aws.spans_entre,  # noqa: E731
                                    largo_respuesta=E.LARGO_RESPUESTA)
    comun = dict(medir=medir, ejecutar_sql=aws.ejecutar_sql, reportes=aws.reportes, tope=t, referencias=E.CR.cargar())
    frio = E.correr(calentamiento, en_paralelo=True, **comun)
    principal = E.correr(tareas, **comun)
    datos = {"fecha": time.strftime("%Y-%m-%d"), "presupuesto_del_agente": PRESUPUESTO, "entorno": dict(corrida.exigir),
             "acceso": acceso, "calentamiento": frio, "filas": principal, "esperados": esperados,
             "gasto": E.gasto(frio + principal), "tope": {"usd": corrida.tope_usd, "tokens": corrida.tope_tokens},
             "resumen": {"exito": E.resumen_exito(principal), "latencia": E.resumen_latencia(frio + principal),
                         "trayectoria": E.resumen_trayectoria(principal), "costo": E.resumen_costo(frio + principal),
                         "comparacion": E.comparar_con_lineas_base(principal)}}
    print(E.escribir("crudo_eval.json", datos, [aws.cuenta], carpeta=corrida.salida))
    print(escribir_detalle(E, datos, corrida))
    print(json.dumps(datos["resumen"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
