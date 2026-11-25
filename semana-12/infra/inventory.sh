#!/usr/bin/env bash
# English name for inventario.sh (week 12: the resources that still exist in each cloud; read-only). It runs that script with the same arguments.
exec "$(dirname "$0")/inventario.sh" "$@"
