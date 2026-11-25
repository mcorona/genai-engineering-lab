# Week 10 images (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 10 README](../README.md)

The images of activity 5: business information that exists only as a picture, not in the text corpus. The script
draws them from the frozen sources in `../fuentes/` (`grafica_nivel_servicio.json`, `plano_cedis_occidente.json`).
The results are in [`../resultados/imagenes.md`](../resultados/imagenes.md).

- `grafica_nivel_servicio.png`: a bar chart of the service level per distribution center (CEDIS Centro, Occidente
  and Norte) for September 2026, with the value above each bar and the center's name below it.
- `plano_cedis_occidente.png`: a floor plan of CEDIS Occidente (Guadalajara), with receiving docks 1 to 4 and shipping docks 5 to 8,
  the critical-SKU zone next to dock 2 and the quarantine zone in aisle 12.

**Why it is in Spanish:** the labels belong to the fictional Mexican distributor that the lab measures. The test is
whether a model can tie each value or zone to its Spanish label; translating the labels would change what was
measured.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `*.png` | The chart and the floor plan | Written by `../experimentos/imagenes.py`. Read by `../experimentos/imagenes.py`, `../ci/eval_ci.py` and `semana-12/ingesta/construir_paquete.py` |
