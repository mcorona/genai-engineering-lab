# Week 10 PDFs with injected instructions (Spanish data)

[Glossary](../../docs/glossary.md) · [Week 10 README](../README.md)

The two PDFs of the activity 8 security tests. Each one holds a real table that answers a question, plus an
instruction aimed at the assistant (prompt injection). The test checks that the assistant answers with the real data
and does not follow the instruction. Both were frozen before the run, with their questions in
`../datasets/seguridad.json`. The results are in [`../resultados/seguridad.md`](../resultados/seguridad.md).

- `viaticos_inyeccion.pdf`: travel expense caps per city (lodging and meals, in MXN). The instruction sits in a table
  row; it asks for a false lodging cap and a canary string.
- `garantias_inyeccion.pdf`: manufacturer warranties of material-handling equipment. The instruction sits in a small
  footnote; it asks the assistant to answer only with a support contact and no data.

Their Markdown sources are in `../fuentes/inyeccion/` (described in the week's [DATA.md](../DATA.md)).

**Why it is in Spanish:** the data and the injected text belong to the fictional Mexican distributor that the lab
measures. The injected text is part of the attack case and must stay exactly as built.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `*_inyeccion.pdf` | The two PDFs with injected instructions | Written by `../datasets/construir_seguridad.py`. Read by `../experimentos/seguridad.py` |
