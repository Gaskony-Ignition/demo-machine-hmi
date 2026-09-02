#!/usr/bin/env python3
"""Move the 3D page between a readable .html file and a WebDev Text Resource.

WHY THIS EXISTS

The page used to be page.html sitting beside a doGet.py that read it off disk.
That works, but the Designer cannot see it - Web Dev only lists resources, and
a loose file inside a resource folder is not one. A customer who wants to change
the cell in the Designer could open the Python and nothing else.

A Text Resource fixes that: it appears in Web Dev, opens in a text editor with a
content-type of text/html, and is served directly at its own URL with no Python
in the way. The catch is how it is stored:

    config.json = {"resource-type": "text-resource",
                   "content-type": "text/html",
                   "text": "<the entire page as one JSON string>"}

44 KB of HTML as an escaped JSON string is fine for Ignition and useless in git -
no diffs, no syntax highlighting, no linting. So the readable file stays the
source of truth in src/, and the resource is generated from it.

USE

    python3 tools/webdev_page.py build      src/cell3d/page.html -> the resource
    python3 tools/webdev_page.py extract    the resource -> src/cell3d/page.html

Run `extract` after editing in the Designer, before committing - otherwise the
next `build` overwrites what was typed there. That is the one rule this split
imposes, and it is why `extract` refuses to run when it would lose changes that
were never built.
"""

import datetime
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir))

SRC = os.path.join(ROOT, "src", "cell3d", "page.html")
RES = os.path.join(ROOT, "project", "com.inductiveautomation.webdev",
                   "resources", "cell3d")
CONFIG = os.path.join(RES, "config.json")
RESOURCE = os.path.join(RES, "resource.json")


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build():
    with open(SRC, encoding="utf-8") as f:
        html = f.read()

    os.makedirs(RES, exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump({"resource-type": "text-resource",
                   "content-type": "text/html",
                   "text": html}, f, indent=2)

    # files[] must list exactly what is in the directory. A file on disk that is
    # not listed, or listed and not present, and the scan skips the resource -
    # silently, and for good.
    resource = {
        "scope": "G",
        "version": 1,
        "restricted": False,
        "overridable": True,
        "files": ["config.json"],
        "attributes": {"lastModification": {"actor": "external",
                                            "timestamp": now()}},
    }
    with open(RESOURCE, "w", encoding="utf-8") as f:
        json.dump(resource, f, indent=2)

    print("built  %s  (%d bytes of HTML, sha %s)"
          % (os.path.relpath(CONFIG, ROOT), len(html), digest(html)))


def extract():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    if cfg.get("resource-type") != "text-resource":
        raise SystemExit("%s is a %r, not a text-resource - nothing to extract"
                         % (CONFIG, cfg.get("resource-type")))
    html = cfg.get("text", "")

    if os.path.exists(SRC):
        with open(SRC, encoding="utf-8") as f:
            current = f.read()
        if current == html:
            print("extract: already identical (sha %s) - nothing to do"
                  % digest(html))
            return

    os.makedirs(os.path.dirname(SRC), exist_ok=True)
    with open(SRC, "w", encoding="utf-8") as f:
        f.write(html)
    print("extracted %s  (%d bytes, sha %s)"
          % (os.path.relpath(SRC, ROOT), len(html), digest(html)))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        build()
    elif cmd == "extract":
        extract()
    else:
        raise SystemExit(__doc__.strip().split("USE")[1].strip())
