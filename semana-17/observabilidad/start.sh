#!/usr/bin/env bash
# English name for arrancar.sh (week 17: the observability stack; --status, --stop, --restart, --sampling, --delete). It runs that script with the same arguments.
exec "$(dirname "$0")/arrancar.sh" "$@"
