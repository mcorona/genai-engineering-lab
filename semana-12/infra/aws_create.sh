#!/usr/bin/env bash
# English name for aws_crear.sh (week 12, AWS: the budget, the service role and the operator role). It runs that script with the same arguments.
exec "$(dirname "$0")/aws_crear.sh" "$@"
