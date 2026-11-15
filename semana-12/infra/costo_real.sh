#!/usr/bin/env bash
# Week 12, activity 10: the week's real cost in AWS, by service and by day, from Cost Explorer. Read-only.
#   ./costo_real.sh [start] [end]      dates YYYY-MM-DD; end exclusive. By default 2026-10-26 to tomorrow.
# Each Cost Explorer API query costs $0.01; this script makes ONE. The data takes 24 to 48 h to
# consolidate, so it is run again on day 2 after the deletion. The cost is for the whole account (so is the
# budget): the services week 12 used are separated from the rest. It is also grouped by record type,
# because the account's promotional credits offset the usage and the net comes out at $0: the real cost is the gross usage.
set -euo pipefail
cd "$(dirname "$0")"; source config.sh
export AWS_PAGER=""
INI=${1:-2026-10-26}; FIN=${2:-$(python3 -c 'import datetime;print(datetime.date.today()+datetime.timedelta(days=1))')}
aws ce get-cost-and-usage --region us-east-1 --time-period Start=$INI,End=$FIN --granularity DAILY \
  --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE Type=DIMENSION,Key=RECORD_TYPE --output json | python3 costo_real.py
echo
echo "Google Cloud (no cost API without a BigQuery export): console > Billing > Reports, project $GCP_PROYECTO,"
echo "  grouped by SKU, from $INI to today: https://console.cloud.google.com/billing/reports?project=$GCP_PROYECTO"
echo "Anthropic API (Haiku 5.5 generator and judge): https://console.anthropic.com/usage   ·   OpenAI (answer relevancy embeddings in CI): https://platform.openai.com/usage"
