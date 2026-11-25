# Week 18 data (Spanish data)

[Glossary](../glossary.md) · [Week 18 README](../../semana-18/README.md)

Week 18's data file outside a results folder: the seals of the whiteboard design briefs (activity 6). Each brief is
generated at random and sealed before any rehearsal. Its text lives only in a git-ignored folder (`pizarra/.sellados/`),
and the repository keeps its SHA-256. A brief revealed later can then be shown to be the one sealed earlier. How the
kit is used is in [`pizarra/kit.md`](../../semana-18/pizarra/kit.md).

**Why it is in Spanish:** only the keys are Spanish. They follow the lab's naming, and the file is kept as written,
because `sellar_casos.py` rewrites it when a brief is revealed and its hashes are the seal. The keys are explained
below.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `pizarra/sellos.json` | The seals: one SHA-256 per sealed brief, its planned use and the time it was revealed | `pizarra/sellar_casos.py` (writes it when sealing; `--revelar` checks a brief against its seal and records the time) |

## Keys

| Key | Meaning |
|---|---|
| `fecha` | When the briefs were sealed (UTC) |
| `metodo` | How each seal is computed |
| `casos` | The sealed briefs, by name (`caso-1` … = case 1 …) |
| `uso` | The planned use of the brief: a rehearsal, the final, or a spare |
| `sha256` | The seal: the SHA-256 of the brief's file |
| `revelado` | When the brief was revealed (UTC); `null` while it is still sealed |
