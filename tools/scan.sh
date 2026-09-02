#!/usr/bin/env bash
# Run the module-testing gateway's project scan, ONE AT A TIME.
#
# Several agents work on this project in parallel. Each deploys only the files
# it owns, but the scan is global and the scan tool drives the gateway web UI
# through a headless browser logged in as one user - two of those at once
# collide. flock serialises them; the wait is a few seconds, the alternative is
# a scan that reports success and applied nothing.
set -euo pipefail
LOCK=/tmp/machine-hmi-demo.scan.lock
TOOL=/Home-Claude/ignition-claude-toolkit/plugins/ignition/skills/scan/tool/scan.js
exec flock -w 180 "$LOCK" timeout 240 node "$TOOL" --gateway module-testing "$@"
