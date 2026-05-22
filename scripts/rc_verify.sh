#!/usr/bin/env bash
set -euo pipefail

export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost,::1}"
export HTTP_PROXY="${HTTP_PROXY:-http://localhost:1087}"
export HTTPS_PROXY="${HTTPS_PROXY:-http://localhost:1087}"

uv run python -m unittest discover -s tests
cargo test
git diff --check
ruby -c Formula/miniviking.rb

cat <<'EOF'

Local RC checks passed.

Before public release, also run the stock OpenViking 0.3.14 v2 ingestion/retrieval
smoke with Gemma E4B, then verify Homebrew install and service lifecycle from a
clean runtime directory.
EOF
