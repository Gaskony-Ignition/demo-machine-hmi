#!/usr/bin/env bash
# Package Machine_HMI_Demo as an importable Ignition 8.3 project zip.
#
#   tools/package.sh              -> build/Machine_HMI_Demo-<version>-dev.zip
#   tools/package.sh --release    -> build/Machine_HMI_Demo-<version>.zip, version stamped
#
# Two things about Ignition project zips that are easy to get wrong and give no
# error when you do:
#
#   1. The zip is made from INSIDE the project directory. A zip whose entries
#      start with "Machine_HMI_Demo/" imports as an empty project.
#   2. Perspective global-props never travels. It carries the rig's own identity
#      provider and session settings, and importing it silently reconfigures the
#      target gateway. This project has none; the exclusion below is a guard so
#      that stays true if one is ever added on a gateway and pulled back.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$ROOT/project"
BUILD="$ROOT/build"
NAME="Machine_HMI_Demo"

RELEASE=0
[[ "${1:-}" == "--release" ]] && RELEASE=1

# The version lives in exactly one place: the script package. Everything else
# derives from it, so a release cannot ship a stale number in its filename.
VERSION="$(grep -oP 'VERSION\s*=\s*[\"'\'']\K[0-9]+\.[0-9]+\.[0-9]+' \
           "$PROJECT_DIR/ignition/script-python/MachineDemo/plant/code.py" | head -1)"
if [[ -z "$VERSION" ]]; then
  echo "package: cannot read VERSION from MachineDemo.plant" >&2
  exit 1
fi

if [[ $RELEASE -eq 1 ]]; then
  TITLE="Machine HMI Demo $VERSION"
  SUFFIX="v$VERSION"
  ZIP="$BUILD/${NAME}-${VERSION}.zip"
else
  TITLE="Machine HMI Demo $VERSION (dev)"
  SUFFIX="dev"
  ZIP="$BUILD/${NAME}-${VERSION}-dev.zip"
fi

# Stamp the version into the project Title AND the end of the Description, so a
# gateway shows which release it is running: the Config -> Projects grid shows
# only the Description, the Title shows in the Edit drawer and on Perspective
# launch surfaces. The project NAME is never touched - it breaks URLs.
python3 - "$PROJECT_DIR/project.json" "$TITLE" "$SUFFIX" <<'PY'
import json, re, sys
path, title, suffix = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as fh:
    p = json.load(fh)
p["title"] = title
desc = re.sub(r'\s*·\s*(v[0-9]+\.[0-9]+\.[0-9]+|dev)\s*$', '', p["description"]).rstrip()
p["description"] = desc + " · " + suffix
with open(path, "w") as fh:
    json.dump(p, fh, indent=2)
    fh.write("\n")
print("stamped:", title)
PY

mkdir -p "$BUILD"
rm -f "$ZIP"

( cd "$PROJECT_DIR" && zip -q -r "$ZIP" . \
    -x '.gaskony/*' \
    -x '*/global-props/*' \
    -x '*.pyc' -x '.DS_Store' )

# Prove the zip is rooted correctly rather than trusting the -r flag: the first
# entry must be a resource directory, never the project name.
FIRST="$(unzip -Z1 "$ZIP" | head -1)"
if [[ "$FIRST" == "$NAME/"* ]]; then
  echo "package: zip is rooted at $NAME/ and would import empty" >&2
  exit 1
fi
if unzip -Z1 "$ZIP" | grep -q 'global-props'; then
  echo "package: global-props leaked into the zip" >&2
  exit 1
fi
if ! unzip -Z1 "$ZIP" | grep -q 'webdev/resources/lib/three.min.js'; then
  echo "package: the vendored 3D library is missing - the 3D page would not render offline" >&2
  exit 1
fi

echo "package: $ZIP"
echo "         $(unzip -Z1 "$ZIP" | wc -l) entries, $(du -h "$ZIP" | cut -f1)"
