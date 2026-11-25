#!/usr/bin/env bash
# English name for aws_borrar.sh (week 12, AWS: deletes everything the week creates; a dry run unless --confirm). It runs that script with the same arguments.
exec "$(dirname "$0")/aws_borrar.sh" "$@"
