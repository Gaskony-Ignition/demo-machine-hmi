#!/usr/bin/env bash
# Run the module-testing gateway's project scan, ONE AT A TIME.
#
# Several agents work on this project in parallel. Each deploys only the files
# it owns, but the scan is global and the scan tool drives the gateway web UI
# through a headless browser logged in as one user - two of those at once
# collide. flock serialises them; the wait is a few seconds, the alternative is
# a scan that reports success and applied nothing.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Topology lives in a gitignored local file, not in the repo - see
# env.example.sh for why.
if [[ -f "$HERE/env.local.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HERE/env.local.sh"
else
  echo "scan: no tools/env.local.sh - copy tools/env.example.sh and edit it" >&2
  exit 1
fi

LOCK=/tmp/machine-hmi-demo.scan.lock
exec flock -w 180 "$LOCK" timeout 240 \
  node "$GW_SCAN_TOOL" --gateway "$GW_SCAN_NAME" "$@"
