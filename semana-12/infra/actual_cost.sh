#!/usr/bin/env bash
# English name for costo_real.sh (week 12, AWS: the real cost by service and by day, from Cost Explorer; read-only). It runs that script with the same arguments.
exec "$(dirname "$0")/costo_real.sh" "$@"
