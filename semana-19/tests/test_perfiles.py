"""Week 19, activity 2: lab and prod differ only in the keys of one config file ($0, no AWS)."""
from __future__ import annotations

import json
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
CFG = json.loads((S19 / "spike" / "perfiles.json").read_text(encoding="utf-8"))


def diferencias() -> dict:
    lab, prod = CFG["lab"], CFG["prod"]
    return {k: (lab[k], prod[k]) for k in lab if lab[k] != prod[k]}


def test_los_dos_perfiles_tienen_las_mismas_claves():
    assert set(CFG["lab"]) == set(CFG["prod"])


def test_las_diferencias_estan_listadas():
    d = diferencias()
    assert set(d) >= {"politica_borrado", "ventana_borrado_llave_dias", "retencion_logs_dias", "azs",
                      "multi_az_bd", "api", "waf", "proteccion_borrado_bd"}


def test_prod_es_igual_o_mas_estricto_en_proteccion():
    prod, lab = CFG["prod"], CFG["lab"]
    assert prod["politica_borrado"] == "RETAIN" and lab["politica_borrado"] == "DESTROY"
    assert prod["ventana_borrado_llave_dias"] >= lab["ventana_borrado_llave_dias"]
    assert prod["retencion_logs_dias"] >= lab["retencion_logs_dias"]
    assert prod["azs"] >= lab["azs"]
    assert prod["multi_az_bd"] is True and prod["proteccion_borrado_bd"] is True
    assert prod["waf"] is True and prod["api"] == "REST"


def test_las_claves_del_spike_existen_y_difieren_donde_se_sintetiza():
    for k in CFG["claves_usadas_en_spike"]:
        assert k in CFG["lab"] and k in CFG["prod"]
    assert CFG["lab"]["politica_borrado"] != CFG["prod"]["politica_borrado"]
    assert CFG["lab"]["ventana_borrado_llave_dias"] != CFG["prod"]["ventana_borrado_llave_dias"]


def test_el_app_cdk_lee_el_archivo_y_no_tiene_valores_fijos_de_perfil():
    texto = (S19 / "spike" / "cdk" / "app.py").read_text(encoding="utf-8")
    assert "perfiles.json" in texto and 'PERFIL = os.environ.get("PERFIL", "lab")' in texto
    assert "pending_window=cdk.Duration.days(CFG[" in texto
