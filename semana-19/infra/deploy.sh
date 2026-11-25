#!/usr/bin/env bash
# English name for desplegar.sh (week 19: deploys the foundation stacks; a simulation unless --diff or --yes). It runs that script with the same arguments.
exec "$(dirname "$0")/desplegar.sh" "$@"
