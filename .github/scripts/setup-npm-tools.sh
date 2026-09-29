#!/usr/bin/env bash
# Install the npm-distributed check tools and convert the spec to JSON.
#
# Spectral, Redocly CLI and markdownlint-cli2 are pinned, with their whole
# dependency tree, by .github/scripts/package-lock.json: `npm ci` installs
# exactly the locked versions, verifies every package against its sha512
# integrity, and refuses to run when package.json and the lock disagree.
# Package install scripts are disabled. The tools go under $RUNNER_TEMP,
# outside the checkout, so no check ever scans node_modules.
#
# Then openapi/openapi.yaml is bundled to $RUNNER_TEMP/build/openapi.json with
# the pinned Redocly CLI, for the standard-library-only Python checks.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${RUNNER_TEMP:?RUNNER_TEMP must be set}"
tools="${RUNNER_TEMP}/tools"
build="${RUNNER_TEMP}/build"
mkdir -p "$tools" "$build"

cp "$here/package.json" "$here/package-lock.json" "$tools/"
npm ci --prefix "$tools" --ignore-scripts --no-audit --no-fund
bin="$tools/node_modules/.bin"
if [ -n "${GITHUB_PATH:-}" ]; then
  echo "$bin" >> "$GITHUB_PATH"
fi
# No usage data from the tools, also when this runs in a called workflow.
export REDOCLY_TELEMETRY=off REDOCLY_SUPPRESS_UPDATE_NOTICE=true
if [ -n "${GITHUB_ENV:-}" ]; then
  printf 'REDOCLY_TELEMETRY=off\nREDOCLY_SUPPRESS_UPDATE_NOTICE=true\n' >> "$GITHUB_ENV"
fi
npm ls --prefix "$tools" --depth=0

if [ -f openapi/openapi.yaml ]; then
  "$bin/redocly" bundle openapi/openapi.yaml --ext json --output "$build/openapi.json"
else
  echo "openapi/openapi.yaml is missing" >&2
  exit 1
fi
