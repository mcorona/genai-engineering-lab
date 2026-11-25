#!/usr/bin/env bash
# English name for arrancar.sh (LegacyBridge v1: the bring-up; --status, --stop). It runs that script with the same arguments.
exec "$(dirname "$0")/arrancar.sh" "$@"
