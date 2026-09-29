#!/usr/bin/env bash
# spec-lint: breaking API changes are caught by a machine, on pull requests
# and on pushes. main moves by fast-forward to a branch that passed, so a
# change can reach it without ever being a pull request.
#
# pull_request: oasdiff compares openapi/openapi.yaml in the pull request with
# the spec attached to the latest release (drafts excluded, pre-releases
# included). A breaking change (oasdiff level ERR) passes only when the pull
# request carries the `breaking-change` label AND changes CHANGELOG.md.
#
# push: oasdiff compares openapi/openapi.yaml at the pushed commit with the
# spec as it was before the push: at the previous tip of the branch, or, for
# a new branch, at its merge base with the default branch. A breaking change
# passes only when a commit of the push carries a `Breaking-Change:` trailer
# AND the push changes CHANGELOG.md. The trailer stands in for the label,
# which a push does not have.
#
# oasdiff failing to load either spec is an error, never a pass.
#
# Inputs (environment): EVENT_NAME. pull_request: GH_TOKEN, GITHUB_REPOSITORY,
# BASE_SHA, HEAD_SHA, PR_LABELS (JSON array of label names). push: AFTER_SHA,
# BEFORE_SHA (may be all zeros), DEFAULT_BRANCH.
set -euo pipefail

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Exits 0 when nothing breaks and 1 when oasdiff cannot compare; returns (to
# the acknowledgement checks below) only when the change is breaking.
compare() {
  local rc=0
  oasdiff breaking "$1" openapi/openapi.yaml --fail-on ERR \
    --allow-external-refs=false --format text > "$work/breaking.txt" 2>&1 || rc=$?
  cat "$work/breaking.txt"
  case "$rc" in
    0) echo "breaking-change: ok - no breaking change against $2"; exit 0 ;;
    1) ;;
    *) echo "breaking-change: oasdiff could not compare the specs (exit $rc)"; exit 1 ;;
  esac
}

case "${EVENT_NAME:?}" in
  pull_request)
    : "${GITHUB_REPOSITORY:?}" "${BASE_SHA:?}" "${HEAD_SHA:?}" "${PR_LABELS:?}"
    tag="$(gh release list --repo "$GITHUB_REPOSITORY" --exclude-drafts --limit 1 --json tagName --jq '.[0].tagName // ""')"
    if [ -z "$tag" ]; then
      echo "breaking-change: no published release yet, so there is no baseline to compare against"
      exit 0
    fi
    gh release download "$tag" --repo "$GITHUB_REPOSITORY" --pattern openapi.yaml --dir "$work"
    compare "$work/openapi.yaml" "$tag"
    acknowledged="$(printf '%s' "$PR_LABELS" | python3 -c 'import json, sys; print("yes" if "breaking-change" in json.load(sys.stdin) else "no")')"
    missing="has no 'breaking-change' label"
    range="$BASE_SHA..$HEAD_SHA"
    what="the pull request"
    ;;
  push)
    : "${AFTER_SHA:?}" "${DEFAULT_BRANCH:?}"
    base=""
    if [ -n "${BEFORE_SHA:-}" ] && [ "$BEFORE_SHA" != "0000000000000000000000000000000000000000" ] \
      && git cat-file -e "${BEFORE_SHA}^{commit}" 2>/dev/null; then
      base="$BEFORE_SHA"
    elif git rev-parse -q --verify "origin/${DEFAULT_BRANCH}^{commit}" >/dev/null; then
      base="$(git merge-base "origin/${DEFAULT_BRANCH}" "$AFTER_SHA" || true)"
    fi
    if [ -z "$base" ]; then
      echo "breaking-change: no commit before this push to compare against"
      exit 0
    fi
    if ! git cat-file -e "${base}:openapi/openapi.yaml" 2>/dev/null; then
      echo "breaking-change: openapi/openapi.yaml does not exist at ${base:0:12}, so there is nothing to compare against"
      exit 0
    fi
    git show "${base}:openapi/openapi.yaml" > "$work/base.yaml"
    compare "$work/base.yaml" "${base:0:12}"
    trailers="$(git log --format='%(trailers:key=Breaking-Change,valueonly)' "$base..$AFTER_SHA" | grep -c . || true)"
    acknowledged="$([ "$trailers" -gt 0 ] && echo yes || echo no)"
    missing="has no commit with a 'Breaking-Change:' trailer"
    range="$base..$AFTER_SHA"
    what="the push"
    ;;
  *)
    echo "breaking-change: nothing to compare on a ${EVENT_NAME} event"
    exit 0
    ;;
esac

changelog="$(git diff --name-only "${range%%..*}" "${range##*..}" -- CHANGELOG.md)"
status=0
if [ "$acknowledged" != "yes" ]; then
  echo "breaking-change: $what breaks the API but $missing"
  status=1
fi
if [ -z "$changelog" ]; then
  echo "breaking-change: $what breaks the API but does not change CHANGELOG.md"
  status=1
fi
if [ "$status" -eq 0 ]; then
  echo "breaking-change: ok - $what breaks the API, says so, and updates CHANGELOG.md"
fi
exit "$status"
