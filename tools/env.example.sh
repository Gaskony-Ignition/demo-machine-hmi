# Where THIS machine's gateway is. Copy to env.local.sh and edit.
#
#   cp tools/env.example.sh tools/env.local.sh
#
# env.local.sh is gitignored. Nothing here is secret - it is topology, and
# topology is per-person: the repo should be useful to someone whose gateway
# is somewhere else entirely, and a committed IP address is just a wrong
# answer waiting to be copied.

# The container the gateway runs in, and where it keeps its projects.
GW_CONTAINER="ignition"
GW_PROJECTS="/usr/local/bin/ignition/data/projects"

# The name this gateway is known by in the scan tool's config, and the path to
# that tool. Any way of triggering a Projects "Scan File System" will do -
# the tool is a convenience, not a dependency.
GW_SCAN_NAME="my-gateway"
GW_SCAN_TOOL="$HOME/ignition-claude-toolkit/plugins/ignition/skills/scan/tool/scan.js"

# Base URL, used only by the docs and by hand-testing the WebDev routes.
GW_URL="http://gateway.example:8088"
