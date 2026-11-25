#!/usr/bin/env bash
# English name for revisar_secretos.sh (no credentials in the versioned files; exits with 1 if it finds one). It runs that script with the same arguments.
exec "$(dirname "$0")/revisar_secretos.sh" "$@"
