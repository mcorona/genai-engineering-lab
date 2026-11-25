#!/usr/bin/env bash
# English name for destruir.sh (week 19: tears the stacks down and checks the inventory; a simulation unless --yes). It runs that script with the same arguments.
exec "$(dirname "$0")/destruir.sh" "$@"
