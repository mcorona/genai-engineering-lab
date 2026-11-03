# Activity 2: observability stack (Langfuse v4 self-hosted + OpenTelemetry Collector)

Measured on 2026-11-03 on the Mac (Docker 29.9.2 with 7.7 GiB of memory), **$0 and no model call**. Everything below comes from
[`stack.json`](stack.json), written by [`observabilidad/verificar_stack.py`](../observabilidad/verificar_stack.py) (it needs
Docker, so it runs on the Mac and not in CI), or from [`tests/test_stack.py`](../tests/test_stack.py), which does run in CI.

| File | What it is |
|---|---|
| [`observabilidad/docker-compose.yml`](../observabilidad/docker-compose.yml) | Langfuse web and worker, PostgreSQL, ClickHouse, Redis, MinIO and the Collector. Images by digest (`IMG_*`), named volumes, `restart: unless-stopped` |
| [`observabilidad/collector.yaml`](../observabilidad/collector.yaml) | OTLP (HTTP 4318, gRPC 4317) → `memory_limiter` → `redaction` → `transform/redaccion` → `batch` → JSONL file and Langfuse |
| [`observabilidad/arrancar.sh`](../observabilidad/arrancar.sh) | Writes the random secrets once, resolves the digests from `versiones.json`, starts and waits. Options: `--estado`, `--detener`, `--reiniciar`, `--borrar [--secretos]` |
| `observabilidad/.secretos.env` | 11 random variables, mode 600, git-ignored, never printed (only the count and the key lengths) |

```bash
cd semana-17/observabilidad
./arrancar.sh                    # Langfuse on http://127.0.0.1:3100, OTLP HTTP 127.0.0.1:4318, gRPC 4317, health 13133
./arrancar.sh --reiniciar        # data persists
./arrancar.sh --borrar           # containers, volumes, network and datos/ (keeps .secretos.env)
uv run --group semana17 python verificar_stack.py     # the whole check below; it deletes the stack at the end
```

## The three tests of the plan, and what else was measured

| Test | Result | Source |
|---|---|---|
| A synthetic trace arrives in Langfuse and in the file | **3 observations** (`AGENT`, `GENERATION`, `TOOL`) in Langfuse, and the trace is in `datos/trazas.jsonl` | `traza_1` |
| Canary DSN, OAuth token, bearer token, API key, email, phone and tax ID come out redacted in both | **0 of 7 canaries** in the file or in Langfuse, in every zone checked (table below), and `****` is present in both | `traza_1` |
| The stack is up again after a restart | `--reiniciar` takes **16 s**; all 7 services run, the earlier trace is still in Langfuse and in the file, and a new trace flows | `reinicio` |
| It is fully removed with `--borrar` | **0 containers, 0 volumes, 0 networks** and no `datos/` after 5 s; `.secretos.env` is kept on purpose | `borrado` |

| Extra check | Result | Source |
|---|---|---|
| Start | Ready in **18 s** with the images already pulled; `langfuse-web` reports `(healthy)`; Langfuse 4.72.0 | `arranque` |
| Exposure | Exactly four host ports, all on `127.0.0.1`: 3100, 4317, 4318 and 13133. PostgreSQL, ClickHouse, Redis, MinIO and the worker publish none. All 7 images run by digest | `exposicion` |
| Langfuse down | While Langfuse is stopped the trace still reaches the file; once it is back (4 s), Langfuse has all **3 observations within 9 s of the stop** (the check polls every 3 s), through the Collector's retry queue, with no canary | `caida_de_langfuse` |
| Memory | **3002 MiB** for the 7 containers right after the traces (the plan estimated about 4 GB) | `memoria_mib_con_carga` |
| OTLP ports | HTTP 4318 accepts a request (200). gRPC 4317 only **accepts a TCP connection**: no gRPC client is installed in the lab | `otlp` |

## Redaction, zone by zone

The canaries were seeded in every zone of a trace (resource, span name, string and list attributes, span status message,
event name, event attributes and a recorded exception). `redaction` alone is the activity 1 pipeline; the final pipeline adds
`transform/redaccion`. Both columns are reproduced by [`tests/test_stack.py`](../tests/test_stack.py) against the real
processors.

| Zone | `redaction` alone | Final pipeline |
|---|---|---|
| Resource attributes | masked | masked |
| Span attributes (strings) | masked | masked |
| Span event attributes (including the exception message) | masked | masked |
| **Span name** | **leaks** (email, tax ID) | masked |
| **Span status message** | **leaks** (phone, API key) | masked |
| **Span event name** | **leaks** (email) | masked |
| **Span attributes that are lists** | **leaks** | **leaks: known gap** |

In Langfuse, the same canaries are absent from `name`, `statusMessage`, `metadata`, `input` and `output` of the 3 observations.

## Findings that change later activities

1. **List attributes are not redacted** (activity 3 and activity 9). Neither `redaction` nor OTTL's `replace_all_patterns` reads a
   list, so `["a@b.com", "postgresql://..."]` reaches the file and Langfuse intact (`hueco_listas` in `stack.json`; a test pins
   it, and fails the day it is closed). The fix is measured: with `allow_all_keys: false` and an `allowed_keys` list,
   `redaction` drops every key that is not allowed, lists included. It needs the final span shape, so activity 3 locks the
   shape (no free text in lists) and activity 9 switches the Collector to the allowlist.
2. **Redaction is not only about attributes.** Span names, status messages and event names carry text too (a tool call named
   after the user's email, an error status with a key). Activity 3 must not put free text there, and the Collector masks it
   as a second layer.
3. **Langfuse's image has no `hostname` and listens only on the container's own address.** The Docker healthcheck uses
   `$HOSTNAME`; `localhost` and `127.0.0.1` refuse the connection. The first version of the healthcheck never turned
   `(healthy)`, which the end-to-end check caught.
4. **A Langfuse outage does not lose traces or block the agent.** The file exporter is independent of Langfuse, and the
   sending queue retries (5 s first, up to 300 s). The retry window is the limit: a longer outage drops what is queued.
5. **Retention is still open (activity 9).** The raw file is bounded by rotation (20 MB, 5 files, 7 days; configured, not
   exercised). Langfuse's own retention needs an entitlement the self-hosted plans lack, so activity 9 uses `trace-deletion`
   or a deletion job of the lab's own.

## What this does not cover

- **CI does not run the stack.** `eval-semana-17` runs `tests/test_stack.py` (static checks, the real redaction processors on the
  Collector binary, and the committed `stack.json`). The end-to-end run needs Docker and about 3 GiB.
- **gRPC was not exercised**, only the TCP listener. **Span links and instrumentation-scope attributes were not seeded.**
- **Restart means stop and start of the containers.** A Docker daemon restart (where `unless-stopped` matters) and a reboot
  were not tried.
- **Langfuse access control is the default of a fresh install** (one user, one project). Per-tenant projects and key rotation
  belong to activity 9.
