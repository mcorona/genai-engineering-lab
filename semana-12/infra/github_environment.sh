#!/usr/bin/env bash
# English name for github_entorno.sh (week 12: the nube-semana12 GitHub environment). It runs that script with the same arguments.
exec "$(dirname "$0")/github_entorno.sh" "$@"
