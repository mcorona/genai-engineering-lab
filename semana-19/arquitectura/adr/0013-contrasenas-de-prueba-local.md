# ADR 0013: test passwords in a local file, not in Secrets Manager

## Context

Two test users (analyst and approver) need passwords for the live smoke test and activity 8. They must never be printed
or committed.

## Alternatives

- **(a)** `semana-19/**/.secretos.env`, mode 600, in `.gitignore`. Written by `usuarios.py`, which prints only lengths.
- **(b)** Secrets Manager. Charged per secret per month; the price is **not in `precios.json`**, so it is **not quoted**.

## Decision

**(a).** Two test users do not justify a paid secret.

## Consequences

- The file is removed by `destruir.sh --todo` together with the test users.
- A test checks that the password does not appear in the repo, the logs or the output of `usuarios.py`.
- Amended 2026-11-21 (activity 9): the file is `~/s19-secretos/usuarios-prueba.env`, outside the repository (mode 600;
  `S19_SECRETOS` overrides it), for both `infra/usuarios.py`, which writes it, and `agentes/comparar.py`, which reads
  it. `usuarios.py` used to default to `semana-19/infra/.secretos.env`, so the new pool's passwords went there while the
  live runs read the deleted pool's. The `.gitignore` entry stays as a guard.

## Costs

- Local file: 0 USD (**M**).
- Secrets Manager (alternative): **N**, not priced in `precios.json`.
