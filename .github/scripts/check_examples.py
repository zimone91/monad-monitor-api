#!/usr/bin/env python3
"""examples: the captured responses in examples/ and the spec agree.

For every operation whose 200 response is application/json:

  1. the media type carries examples.live with
       summary     "Live response, captured <ISO 8601 UTC>"
       description "<exact command>; <truncation note or 'not truncated'>"
     and the command requests this operation from api.zim.one;
  2. examples/<operationId>.json exists, is 2-space JSON with a trailing
     newline, and is JSON-equal to examples.live.value;
  3. every key in the example is declared in the response schema
     (undocumented-field check, see oas.py);
  4. examples/README.md names the file on a row that carries the same
     capture time.

Every examples/*.json file must belong to such an operation. Schema validity
of the examples is checked by Spectral in the same job (oas3-valid-media-example
at error severity, .github/scripts/examples.spectral.yaml).

Standard library only. Exit 0 only when every check passed; the number of
validated examples is printed and, with --github-output, written to
$GITHUB_OUTPUT as `validated=<n>`.
"""

import argparse
import datetime
import json
import os
import re
import sys
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oas  # noqa: E402

SUMMARY_RE = re.compile(r"^Live response, captured (?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)$")
URL_RE = re.compile(r"https://api\.zim\.one(?P<rest>/[^\s'\"`]*)?")


def parse_utc(ts):
    try:
        datetime.datetime.strptime(ts.split(".")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
        return True
    except ValueError:
        return False


def command_path(description):
    """Return (command, note, request path without /v1, query) or raise."""
    if "; " not in description:
        raise ValueError("description is not '<exact command>; <truncation note>'")
    command, note = description.rsplit("; ", 1)
    if not note.strip():
        raise ValueError("truncation note is empty (write 'not truncated' when nothing was cut)")
    urls = URL_RE.findall(command)
    match = URL_RE.search(command)
    if not match or len(urls) != 1:
        raise ValueError("the command must request exactly one https://api.zim.one URL, found %d" % len(urls))
    parts = urlsplit(match.group(0))
    path = parts.path
    if path == "/v1" or path.startswith("/v1/"):
        path = path[3:]
    return command, note, path or "/", parts.query


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", required=True, help="the spec as JSON (redocly bundle --ext json)")
    parser.add_argument("--examples-dir", default="examples")
    parser.add_argument("--capture-table", default="examples/README.md")
    parser.add_argument("--github-output", action="store_true", help="write validated=<n> to $GITHUB_OUTPUT")
    args = parser.parse_args(argv)

    try:
        doc = oas.load_json(args.spec)
    except oas.CannotCheck as exc:
        print("CANNOT CHECK: %s" % exc)
        return 1

    errors = []
    validated = 0
    expected_files = set()
    try:
        with open(args.capture_table, encoding="utf-8") as fh:
            table_lines = fh.read().splitlines()
    except OSError as exc:
        table_lines = None
        errors.append("%s: cannot read the capture table (%s)" % (args.capture_table, exc))

    json_ops = 0
    for method, path, op in oas.operations(doc):
        media = oas.json_media(doc, op)
        if media is None:
            continue
        json_ops += 1
        op_id = op.get("operationId")
        where = "%s %s" % (method.upper(), path)
        if not op_id:
            errors.append("%s: no operationId, so no examples/<operationId>.json can be matched" % where)
            continue
        where = "%s (%s)" % (where, op_id)
        name = "%s.json" % op_id
        expected_files.add(name)
        failed = False

        live = (media.get("examples") or {}).get("live")
        if not isinstance(live, dict) or "value" not in live:
            errors.append("%s: 200 application/json has no examples.live with a value" % where)
            continue
        summary = live.get("summary") or ""
        match = SUMMARY_RE.match(summary)
        if not match or not parse_utc(match.group("ts")):
            errors.append("%s: examples.live.summary must be 'Live response, captured <ISO 8601 UTC>', got %r" % (where, summary))
            failed = True
        captured = match.group("ts") if match else None
        try:
            _cmd, _note, req_path, _query = command_path(live.get("description") or "")
            if not oas.path_regex(path).match(req_path):
                errors.append("%s: the command in examples.live.description requests %s, not this operation" % (where, req_path))
                failed = True
        except ValueError as exc:
            errors.append("%s: examples.live.description: %s" % (where, exc))
            failed = True

        file_path = os.path.join(args.examples_dir, name)
        try:
            with open(file_path, encoding="utf-8") as fh:
                raw = fh.read()
            body = json.loads(raw)
        except (OSError, ValueError) as exc:
            errors.append("%s: %s: %s" % (where, file_path, exc))
            continue
        canonical = json.dumps(body, indent=2, ensure_ascii=False) + "\n"
        if raw != canonical:
            errors.append("%s: %s is not 2-space JSON with one trailing newline" % (where, file_path))
            failed = True
        if not oas.json_equal(body, live["value"]):
            errors.append("%s: %s differs from examples.live.value in the spec" % (where, file_path))
            failed = True

        schema = media.get("schema")
        if schema is None:
            errors.append("%s: 200 application/json has no schema" % where)
            failed = True
        else:
            try:
                problems = oas.dedupe_paths(oas.undocumented(doc, body, schema))
            except oas.CannotCheck as exc:
                errors.append("%s: CANNOT CHECK undocumented fields: %s" % (where, exc))
                problems = []
                failed = True
            for problem in problems:
                errors.append("%s: undocumented field %s" % (where, problem))
                failed = True

        if table_lines is not None:
            rows = [line for line in table_lines if name in line]
            if not rows:
                errors.append("%s: %s has no row in %s" % (where, name, args.capture_table))
                failed = True
            elif captured and not any(captured in row for row in rows):
                errors.append("%s: the row for %s in %s does not carry the capture time %s from the spec" % (where, name, args.capture_table, captured))
                failed = True

        if not failed:
            validated += 1
            print("ok   %-34s %s" % (name, where))

    try:
        present = sorted(f for f in os.listdir(args.examples_dir) if f.endswith(".json"))
    except OSError as exc:
        present = []
        errors.append("cannot list %s: %s" % (args.examples_dir, exc))
    for orphan in sorted(set(present) - expected_files):
        errors.append("%s/%s: no operation in the spec has a JSON 200 response for operationId %r" % (args.examples_dir, orphan, orphan[:-5]))

    if json_ops == 0:
        errors.append("the spec has no operation with a 200 application/json response: nothing was checked")

    if args.github_output and not errors:
        out = os.environ.get("GITHUB_OUTPUT")
        if not out:
            errors.append("--github-output given but GITHUB_OUTPUT is not set")
        else:
            with open(out, "a", encoding="utf-8") as fh:
                fh.write("validated=%d\n" % validated)

    for error in errors:
        print("FAIL %s" % error)
    if errors:
        print("examples: %d problem(s); %d of %d example(s) passed every check" % (len(errors), validated, json_ops))
        return 1
    print("examples: ok - %d of %d example(s) validated (%d file(s) in %s)" % (validated, json_ops, len(present), args.examples_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
