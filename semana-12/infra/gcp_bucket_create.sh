#!/usr/bin/env bash
# English name for gcp_bucket_crear.sh (week 12, Google Cloud: the document bucket and its permissions). It runs that script with the same arguments.
exec "$(dirname "$0")/gcp_bucket_crear.sh" "$@"
