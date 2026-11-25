#!/usr/bin/env bash
# English name for preparar.sh (week 15: one virtual environment per framework). It runs that script with the same arguments.
exec "$(dirname "$0")/preparar.sh" "$@"
