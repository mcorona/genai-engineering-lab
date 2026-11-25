#!/usr/bin/env bash
# English name for arrancar.sh (week 14: Keycloak with the legacybridge realm; --stop, --delete). It runs that script with the same arguments.
exec "$(dirname "$0")/arrancar.sh" "$@"
