#!/usr/bin/env bash
# English name for jalar_imagenes.sh (week 17: pulls the pinned container images). It runs that script with the same arguments.
exec "$(dirname "$0")/jalar_imagenes.sh" "$@"
