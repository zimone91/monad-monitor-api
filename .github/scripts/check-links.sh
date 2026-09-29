#!/usr/bin/env bash
# links / links-weekly: lychee over every tracked Markdown file and over the
# page built from the spec (the same single HTML file pages.yml publishes).
# Configuration and exclusions, each with its reason: lychee.toml.
# Extra arguments are passed to lychee (CI passes none).
set -euo pipefail

: "${RUNNER_TEMP:?RUNNER_TEMP must be set}"
site="$RUNNER_TEMP/link-check-site"
mkdir -p "$site"
redocly build-docs openapi/openapi.yaml --output "$site/index.html" --disableGoogleFont

count="$(git ls-files '*.md' | wc -l | tr -d ' ')"
if [ "$count" -eq 0 ]; then
  echo "links: no Markdown file is tracked: nothing to check" >&2
  exit 1
fi
echo "links: $count Markdown file(s) and the built page"
{ git ls-files -z '*.md'; printf '%s\0' "$site/index.html"; } \
  | xargs -0 lychee --config lychee.toml --no-progress "$@"
