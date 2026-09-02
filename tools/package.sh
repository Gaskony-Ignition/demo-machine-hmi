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

# Build to a temporary name and only move it into place once every check below
# has passed. A half-written archive at the real path is indistinguishable from
# a finished one, and the one thing worse than a build that fails is a build
# that leaves a plausible-looking zip behind after failing.
# mktemp reserves the name collision-safely, but it also CREATES the file, and
# zip appends to an existing archive - a zero-byte one is "Zip file structure
# invalid". Take the name, drop the empty file, let zip create it properly.
TMPZIP="$(mktemp "${BUILD}/.package.XXXXXX.zip")"
rm -f "$TMPZIP"
trap 'rm -f "$TMPZIP"' EXIT

( cd "$PROJECT_DIR" && zip -q -r "$TMPZIP" . \
    -x '.gaskony/*' \
    -x '*/global-props/*' \
    -x '*.pyc' -x '.DS_Store' )

# zip exits 0 on some partial writes; make it prove the archive reads back.
unzip -t "$TMPZIP" >/dev/null || { echo "package: archive failed its integrity test" >&2; exit 1; }

# Count what went in against what is on disk, so a silently short archive is
# caught by arithmetic rather than by spot-checking a few known files.
ON_DISK="$(cd "$PROJECT_DIR" && find . -type f \
             ! -path './.gaskony/*' ! -path '*/global-props/*' \
             ! -name '*.pyc' ! -name '.DS_Store' | wc -l)"
IN_ZIP="$(unzip -Z1 "$TMPZIP" | grep -vc '/$' || true)"
if [[ "$ON_DISK" -ne "$IN_ZIP" ]]; then
  echo "package: archive has $IN_ZIP files but $ON_DISK are on disk" >&2
  exit 1
fi

# List the archive ONCE into a variable and check that.
#
# Do not pipe `unzip -Z1` into `grep -q` under `set -o pipefail`: grep -q exits
# the instant it matches, unzip is killed by SIGPIPE, and the PIPELINE reports
# non-zero even though the match succeeded. Wrapped in `if !`, that turns a
# PASSING check into a failure, intermittently, depending on whether unzip had
# finished writing. It cost a "the vendored 3D library is missing" failure on a
# file that was present in the tree, on the gateway and in git.
LISTING="$(unzip -Z1 "$TMPZIP")"

FIRST="$(printf '%s\n' "$LISTING" | head -1)"
if [[ "$FIRST" == "$NAME/"* ]]; then
  echo "package: zip is rooted at $NAME/ and would import empty" >&2
  exit 1
fi
if printf '%s\n' "$LISTING" | grep -q 'global-props'; then
  echo "package: global-props leaked into the zip" >&2
  exit 1
fi
if ! printf '%s\n' "$LISTING" | grep -q 'webdev/resources/lib/three.min.js'; then
  echo "package: the vendored 3D library is missing - the 3D page would not render offline" >&2
  exit 1
fi

# Every resource directory must carry a resource.json whose files[] matches the
# directory exactly. A missing lastModification, or a file present on disk but
# absent from files[], makes the gateway's scan skip that resource for good --
# silently, with the import reporting success. Cheaper to fail here than to find
# out that one view is missing in front of a customer.
python3 - "$TMPZIP" <<'PY'
import zipfile, json, posixpath, sys
z = zipfile.ZipFile(sys.argv[1])
names = set(z.namelist())
bad = []
for r in [n for n in names if n.endswith("resource.json")]:
    d = posixpath.dirname(r)
    try:
        cfg = json.loads(z.read(r))
    except Exception as e:
        bad.append("%s: invalid JSON (%s)" % (r, e))
        continue
    if "lastModification" not in cfg.get("attributes", {}):
        bad.append("%s: no attributes.lastModification - the scan will skip it" % r)
    listed = cfg.get("files", [])
    for f in listed:
        if posixpath.join(d, f) not in names:
            bad.append("%s: lists '%s' which is not in the zip" % (r, f))
    for n in names:
        if posixpath.dirname(n) == d and not n.endswith("/"):
            f = posixpath.basename(n)
            if f != "resource.json" and f not in listed:
                bad.append("%s: '%s' is in the directory but not in files[]" % (r, f))
if bad:
    print("package: resource manifest problems:", file=sys.stderr)
    for b in bad:
        print("  - " + b, file=sys.stderr)
    sys.exit(1)
print("         %d resource manifests verified" % sum(1 for n in names if n.endswith("resource.json")))
PY

# Everything passed: publish the archive under its real name.
mv "$TMPZIP" "$ZIP"
trap - EXIT

echo "package: $ZIP"
echo "         $(unzip -Z1 "$ZIP" | wc -l) entries, $(du -h "$ZIP" | cut -f1)"
