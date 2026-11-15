"""Verification of an agent answer against the gold set (used by the pilot and by the activity 6 evaluation).

- state: the agent's against estado_esperado.
- execution accuracy, per key: the SQL the agent reported is validated with the guard (as analista) and re-executed
  in full; its rows are compared with the expected ones using week 7's comparator (results_match).
- coherence, per key: the value the agent reported matches what its own SQL returns (it detects answers
  that say something different from what the data shows).
- task success: the correct state and, if an answer was expected, every key exact.
"""
import importlib.util
from pathlib import Path

from herramientas import Contexto, Herramientas
from herramientas.herramientas import ErrorHerramienta

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("run_eval7", RAIZ / "semana-07" / "run_eval.py")
re7 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(re7)


def _filas_de_valor(valor):
    if isinstance(valor, list):
        return [tuple(v) if isinstance(v, (list, tuple)) else (v,) for v in valor]
    return [(valor,)]


def verificar(tarea: dict, final: dict | None, conexion, estado: str) -> dict:
    h = Herramientas(Contexto.de_usuario("analista", conexion=conexion, timeout_ms=15000))
    out = {"estado_ok": estado == tarea["estado_esperado"], "claves": {}}
    reportadas = {x["clave"]: x for x in (final or {}).get("resultados", [])}
    for clave, s in tarea.get("salida", {}).items():
        res = {"reportada": clave in reportadas, "exacta": False, "coherente": False, "error": None}
        if clave in reportadas:
            sql = reportadas[clave]["sql"]
            try:
                h._guard(sql)
                _, filas = h._correr(sql)
                res["exacta"] = re7.results_match([tuple(f) for f in s["esperado"]], filas, s.get("orden", False))
                res["coherente"] = re7.results_match(filas, _filas_de_valor(reportadas[clave]["valor"]), False) or (
                    len(filas) == 1 and len(filas[0]) == 1 and re7.results_match(filas, [(reportadas[clave]["valor"],)]))
            except ErrorHerramienta as e:
                res["error"] = e.tipo
            except Exception as e:  # noqa: BLE001  a SQL statement that breaks the verifier counts as a non-exact key
                res["error"] = f"verificacion: {type(e).__name__}"
        out["claves"][clave] = res
    claves = out["claves"].values()
    out["exito"] = out["estado_ok"] and (tarea["estado_esperado"] != "respondida" or all(c["exacta"] for c in claves))
    out["exactitud_claves"] = sum(c["exacta"] for c in claves) / len(claves) if claves else None
    out["coherencia_claves"] = sum(c["coherente"] for c in claves) / len(claves) if claves else None
    return out
