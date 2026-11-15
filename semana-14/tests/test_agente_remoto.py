"""Activity 7: task selection and the leak detector of the remote harness (no API, $0)."""
import importlib.util
from types import SimpleNamespace

from conftest import S14

spec = importlib.util.spec_from_file_location("remoto14", S14 / "agente_remoto" / "correr.py")
remoto = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remoto)


def test_subconjunto_estratificado():
    ts = remoto.tareas()
    assert len(ts) == 40 and sum(t["lang"] == "es" for t in ts) == 20
    por_tipo = {k: len(v) for k, v in remoto.SUBCONJUNTO.items()}
    assert por_tipo == {"simple": 5, "regla": 5, "compuesta": 4, "valores": 2, "ambigua": 2, "sin_respuesta": 2}
    assert {t["tipo"] for t in ts} == set(remoto.SUBCONJUNTO)
    sin = remoto.tareas_sin_scope()
    assert len(sin) == 8 and {t["usuario"] for t in sin} == {"almacenista", "vendedor"}


def _cliente(*llamadas):
    return SimpleNamespace(llamadas=list(llamadas))


def test_fuga_detecta_el_dato_en_la_respuesta():
    t = next(x for x in remoto.tareas_sin_scope() if x["id"] == "s03-es")
    nombre = t["salida"]["filas"]["esperado"][0][0]
    r = SimpleNamespace(final={"respuesta": f"El proveedor es {nombre}"}, estado="respondida")
    f = remoto.fuga(t, r, _cliente())
    assert f["fuga"] and nombre in f["valores_filtrados"]


def test_fuga_detecta_lectura_prohibida_y_reconoce_la_negativa():
    t = next(x for x in remoto.tareas_sin_scope() if x["id"] == "v03-en")
    ok = {"herramienta": "ejecutar_sql", "argumentos": {"sql": "SELECT prv_nm FROM prvmst"}, "ok": True, "salida": "{}"}
    assert remoto.fuga(t, SimpleNamespace(final=None, estado="respondida"), _cliente(ok))["lecturas_prohibidas"]
    negada = {"herramienta": "ejecutar_sql", "argumentos": {"sql": "SELECT prv_nm FROM prvmst"}, "ok": False,
              "salida": '{"ok": false, "error": {"tipo": "permiso_denegado"}}'}
    f = remoto.fuga(t, SimpleNamespace(final={"respuesta": "No tengo acceso."}, estado="abstenida"), _cliente(negada))
    assert not f["fuga"] and f["termino_bien"] and f["denegadas"] == ["permiso_denegado"]


def test_wilson():
    assert remoto._wilson(36, 40) == (0.769, 0.96)
