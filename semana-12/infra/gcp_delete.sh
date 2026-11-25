#!/usr/bin/env bash
# English name for gcp_borrar.sh (week 12, Google Cloud: deletes everything the week creates; a dry run unless --confirm). It runs that script with the same arguments.
exec "$(dirname "$0")/gcp_borrar.sh" "$@"
