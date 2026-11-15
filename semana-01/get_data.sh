#!/usr/bin/env bash
# Downloads the week 1 datasets (not versioned: input.txt is 1 MB).
set -euo pipefail
cd "$(dirname "$0")"
curl -fL -o names.txt https://raw.githubusercontent.com/karpathy/makemore/master/names.txt
curl -fL -o input.txt https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt
wc -l names.txt input.txt
