#!/usr/bin/env bash
# Assemble the Pages site from the parts produced in this workflow run.
#
# Usage: assemble-site.sh PARTS_DIR SITE_DIR
#   PARTS_DIR/checks/   the `badges` artifact of ci.yml (called by pages.yml):
#                       badges/{checks,endpoints,examples,openapi,status}.json
#                       and checks-detail.json
#   PARTS_DIR/contract/ the `contract` artifact of contract-live:
#                       badges/contract.json and contract.json
#
# The page itself is built here from openapi/openapi.yaml. A Pages deployment
# replaces the whole site, so a missing part fails the build: the previous
# deployment then stays up, and its dates show its age.
set -euo pipefail

parts="${1:?usage: assemble-site.sh PARTS_DIR SITE_DIR}"
site="${2:?usage: assemble-site.sh PARTS_DIR SITE_DIR}"
rm -rf "$site"
mkdir -p "$site/badges"

redocly build-docs openapi/openapi.yaml --output "$site/index.html" --disableGoogleFont

# SPEC 3.6: the page loads nothing from another host. build-docs points it at
# Redoc's bundle on cdn.redocly.com, and the bundle's sidebar credit loads its
# logo from cdn.redoc.ly. Both files, and the license file the bundle names,
# are fetched here at build time instead, checked against the pins below, and
# served from this site. The integrity attribute the pinned Redocly CLI wrote
# into the page must match the fetched bundle, so a CLI upgrade that moves to
# another Redoc fails here until the pins are updated. The edited bundle (one
# URL replaced, by site_page.py localize) has a pin of its own.
redoc_url="https://cdn.redocly.com/redoc/v2.5.4/bundles/redoc.standalone.js"
redoc_sha256=dcaf76612bc4a3fbcc923a8966dee2f6146a5f32e5ce1b6f02dd60cbbf89500b
redoc_license_sha256=eed602ec32e00b2b9df1984fbcc26a687b1b3193ec01961389c4b8439e6edf73
redoc_logo_url="https://cdn.redoc.ly/redoc/logo-mini.svg"
redoc_logo_sha256=1dab4315f8de2177b2b2726b29e84a26314c69cd27d692228947c0058793d5a7
redoc_served_sha256=7252b29130e10e8fd4f4392a704766c24d45ea001626f07f80bbc5d6c3d6dac0
curl -fsSL --retry 3 --proto '=https' -o "$site/redoc.standalone.js" "$redoc_url"
curl -fsSL --retry 3 --proto '=https' -o "$site/redoc.standalone.js.LICENSE.txt" "$redoc_url.LICENSE.txt"
curl -fsSL --retry 3 --proto '=https' -o "$site/redoc-logo-mini.svg" "$redoc_logo_url"
(
  cd "$site"
  printf '%s  %s\n' "$redoc_sha256" redoc.standalone.js \
    "$redoc_license_sha256" redoc.standalone.js.LICENSE.txt \
    "$redoc_logo_sha256" redoc-logo-mini.svg | sha256sum -c -
)
expected="$(grep -o 'integrity="sha384-[^"]*"' "$site/index.html" | head -n 1 | sed 's/^integrity="//; s/"$//')"
actual="sha384-$(openssl dgst -sha384 -binary "$site/redoc.standalone.js" | openssl base64 -A)"
if [ "$expected" != "$actual" ]; then
  echo "the page expects Redoc $expected; the pinned bundle is $actual" >&2
  exit 1
fi
python3 .github/scripts/site_page.py localize --page "$site/index.html" \
  --bundle-url "$redoc_url" --bundle-file "$site/redoc.standalone.js" \
  --asset-url "$redoc_logo_url" --asset-local redoc-logo-mini.svg
( cd "$site" && printf '%s  %s\n' "$redoc_served_sha256" redoc.standalone.js | sha256sum -c - )

for name in checks endpoints examples openapi status; do
  cp "$parts/checks/badges/$name.json" "$site/badges/$name.json"
done
cp "$parts/checks/checks-detail.json" "$site/checks-detail.json"
cp "$parts/contract/badges/contract.json" "$site/badges/contract.json"
cp "$parts/contract/contract.json" "$site/contract.json"

python3 - "$site" <<'PY'
import json, os, sys
site = sys.argv[1]
names = ["checks", "contract", "openapi", "status", "endpoints", "examples"]
for name in names:
    with open(os.path.join(site, "badges", name + ".json"), encoding="utf-8") as fh:
        body = json.load(fh)
    if body.get("schemaVersion") != 1 or not all(isinstance(body.get(k), str) and body[k] for k in ("label", "message", "color")):
        sys.exit("badges/%s.json is not a shields endpoint document: %r" % (name, body))
for name in ("contract.json", "checks-detail.json"):
    with open(os.path.join(site, name), encoding="utf-8") as fh:
        json.load(fh)
if os.path.getsize(os.path.join(site, "index.html")) < 1000:
    sys.exit("index.html is suspiciously small")
files = sorted(os.path.relpath(os.path.join(d, f), site) for d, _, fs in os.walk(site) for f in fs)
print("site: %d file(s): %s" % (len(files), ", ".join(files)))
PY

python3 .github/scripts/site_page.py check "$site"
