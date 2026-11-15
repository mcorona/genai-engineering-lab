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

## Costs

- Local file: 0 USD (**M**).
- Secrets Manager (alternative): **N**, not priced in `precios.json`.
