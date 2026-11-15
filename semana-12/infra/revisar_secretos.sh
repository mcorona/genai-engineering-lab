#!/usr/bin/env bash
# Checks that there are no credentials in the repository's versioned (or about to be versioned) files. Exits with 1 if it
# finds any. Patterns: AWS access keys, private keys (Google service accounts), and Google, Anthropic and OpenAI API keys.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
PATRON='(AKIA|ASIA)[0-9A-Z]{16}|aws_secret_access_key *= *[A-Za-z0-9/+]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"private_key_id": *"[0-9a-f]{20,}|AIza[0-9A-Za-z_-]{35}|sk-ant-[A-Za-z0-9_-]{20,}|sk-proj-[A-Za-z0-9_-]{20,}'
# Fake keys used on purpose by the tests of weeks 16 and 17 (canaries that the redaction and the hooks must catch).
# They are exact values: a real key never matches them.
PERMITIDOS='sk-ant-simulado-sin-red-0000000000000000|sk-ant-api03-CANARIOABCDEFGH|sk-ant-api03-valor-de-prueba-123|sk-ant-canario1234567890'
HALLAZGOS=$( { git ls-files; git ls-files --others --exclude-standard; } | grep -v -E '\.(png|jpg|jpeg|pdf|gif)$' | \
  xargs -I{} grep -I -n -E "$PATRON" {} /dev/null 2>/dev/null | grep -v "revisar_secretos.sh" | \
  while IFS= read -r linea; do
    if sed -E "s/($PERMITIDOS)//g" <<<"$linea" | grep -q -E "$PATRON"; then echo "$linea"; fi
  done )
if [ -n "$HALLAZGOS" ]; then echo "Possible credentials:"; echo "$HALLAZGOS" | cut -c1-160; exit 1; fi
echo "No credentials in the repository's files."
