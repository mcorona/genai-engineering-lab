#!/usr/bin/env bash
# English name for gcp_crear.sh (week 12, Google Cloud: the budget and the service account). It runs that script with the same arguments.
exec "$(dirname "$0")/gcp_crear.sh" "$@"
