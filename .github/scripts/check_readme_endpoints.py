#!/usr/bin/env python3
"""readme-endpoints: every API path the documents mention exists in the spec.

A path is "mentioned" when it appears as
  - a URL on https://api.zim.one (with or without the /v1 prefix),
  - an HTTP method followed by a path: `GET /validator/{id}/score`, or
  - an inline code span holding only a path whose first segment is one the
    spec uses (or v1): `/validator/{id}/rewards` is checked, `/usr/bin` is not.
Concrete values match templated segments (/validator/109 matches
/validator/{id}). /openapi.json is served next to the documented operations
and is accepted as the spec itself.

The first file (README.md) must mention at least one path; otherwise the
extraction found nothing and the check fails instead of passing empty.
"""

import argparse
import os
import re
import sys
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oas  # noqa: E402

# The path ends at the first ?, &, #, ), whitespace, quote or backtick: an API
# URL can sit inside another URL's query string (the shields `data` badge).
URL = re.compile(r"https://api\.zim\.one(/[^\s'\"`<>()\[\]|\\?&#]*)?")
METHOD_PATH = re.compile(r"\b(?:GET|HEAD|POST|PUT|PATCH|DELETE|OPTIONS)\s+(/[A-Za-z0-9_{}./:-]*)")
CODE_SPAN = re.compile(r"`(?:(?:GET|HEAD)\s+)?(/[A-Za-z0-9_{}./:-]*(?:\?[^`\s]*)?)`")
SERVED_UNLISTED = {"/openapi.json"}


def normalize(raw):
    path = urlsplit(raw).path if raw.startswith("http") else raw.split("?")[0].split("#")[0]
    path = path.rstrip(".,;:")
    if path == "/v1" or path.startswith("/v1/"):
        path = path[3:]
    if len(path) > 1:
        path = path.rstrip("/")
    return path or "/"


def mentions(text, first_segments):
    for number, line in enumerate(text.splitlines(), 1):
        found = set()
        for match in URL.finditer(line):
            rest = match.group(1) or "/"
            found.add(normalize("https://api.zim.one" + rest))
        for match in METHOD_PATH.finditer(line):
            found.add(normalize(match.group(1)))
        for match in CODE_SPAN.finditer(line):
            raw = match.group(1)
            segment = raw.lstrip("/").split("/")[0].split("?")[0]
            if segment in first_segments or segment == "v1":
                found.add(normalize(raw))
        for path in sorted(found):
            yield number, path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", required=True, help="the spec as JSON")
    parser.add_argument("files", nargs="+", help="README.md first, then other documents")
    args = parser.parse_args(argv)
    try:
        doc = oas.load_json(args.spec)
    except oas.CannotCheck as exc:
        print("CANNOT CHECK: %s" % exc)
        return 1
    paths = list(doc.get("paths") or {})
    templates = [oas.path_regex(p) for p in paths]
    if not templates:
        print("CANNOT CHECK: the spec has no paths")
        return 1
    first_segments = {p.lstrip("/").split("/")[0] for p in paths} | {p.lstrip("/") for p in SERVED_UNLISTED}

    errors, checked, first_count = [], 0, 0
    for index, name in enumerate(args.files):
        try:
            with open(name, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            errors.append("%s: cannot read (%s)" % (name, exc))
            continue
        count = 0
        for number, path in mentions(text, first_segments):
            count += 1
            if path == "/" or path in SERVED_UNLISTED or any(rx.match(path) for rx in templates):
                continue
            errors.append("%s:%d: %s is not a path in the spec" % (name, number, path))
        checked += count
        if index == 0:
            first_count = count
    if first_count == 0 and not errors:
        errors.append("%s mentions no API path: the extraction found nothing to check" % args.files[0])
    for error in errors:
        print("FAIL %s" % error)
    if errors:
        return 1
    print("readme-endpoints: ok - %d path mention(s) in %d file(s) match the spec's %d path(s)" % (checked, len(args.files), len(templates)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
