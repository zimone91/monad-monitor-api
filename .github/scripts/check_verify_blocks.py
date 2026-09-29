#!/usr/bin/env python3
"""The "Verify it yourself" section of README.md, checked and executed.

Contract: inside the section headed exactly `## Verify it yourself`, every
check is one line

    <!-- verify: <Python regular expression> -->

immediately followed by a fenced ```sh block. The block holds read-only
commands against https://api.zim.one/v1 only.

Static checks (always; they need no network):
  - the section exists once and holds at least one check;
  - every ```sh block in it has a verify line, every verify line has a block,
    and every regular expression compiles;
  - each pipeline stage starts with curl, jq, grep or head; no redirection,
    command substitution, variables, `;`, `&&` or `||`;
  - curl sends GET or HEAD only, writes nothing but stdout or /dev/null, and
    requests exactly one URL under https://api.zim.one/v1;
  - one to three curl calls (HTTP requests) per block.

With --run, each block is executed with `bash -euo pipefail -c`, one second
apart, and passes when it exits 0 and its regular expression is found in
stdout (re.M). --json-out writes the per-check result for contract.json.
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time

HEADING = "## Verify it yourself"
VERIFY_LINE = re.compile(r"^<!-- verify: (?P<rx>.+) -->\s*$")
FENCE = re.compile(r"^(?P<fence>`{3,}|~{3,})\s*(?P<info>[^`\s]*)")
API_PREFIX = "https://api.zim.one/v1"
ALLOWED_COMMANDS = {"curl", "jq", "grep", "head"}
MAX_REQUESTS = 3

CURL_SHORT_NOARG = set("sSfiIv")
CURL_SHORT_ARG = set("HwDomXA")
CURL_LONG_NOARG = {"--silent", "--show-error", "--fail", "--fail-with-body", "--include", "--head",
                   "--compressed", "--http1.1", "--http2", "--no-progress-meter", "--verbose"}
CURL_LONG_ARG = {"--header", "--write-out", "--dump-header", "--output", "--max-time", "--request",
                 "--user-agent", "--connect-timeout"}


class Check(object):
    def __init__(self, line, regex, block):
        self.line = line
        self.regex = regex
        self.block = block


def parse(text):
    """Return (checks, errors)."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == HEADING]
    if len(starts) != 1:
        return [], ["README must have exactly one '%s' heading, found %d" % (HEADING, len(starts))]
    begin = starts[0] + 1
    end = len(lines)
    for i in range(begin, len(lines)):
        if re.match(r"^#{1,2}\s", lines[i]):
            end = i
            break
    checks, errors = [], []
    i = begin
    pending = None  # (line number, regex) of a verify line waiting for its block
    while i < end:
        line = lines[i]
        verify = VERIFY_LINE.match(line.strip())
        fence = FENCE.match(line)
        if verify:
            if pending:
                errors.append("line %d: verify line is not followed by a ```sh block" % pending[0])
            pending = (i + 1, verify.group("rx"))
            i += 1
            continue
        if fence:
            marker, info = fence.group("fence"), fence.group("info").lower()
            body, j = [], i + 1
            while j < end and not lines[j].startswith(marker):
                body.append(lines[j])
                j += 1
            if j >= end:
                errors.append("line %d: code fence is not closed inside the section" % (i + 1))
            is_sh = info in ("sh", "bash", "shell", "console")
            if is_sh and info != "sh":
                errors.append("line %d: use ```sh for verify blocks (found ```%s)" % (i + 1, info))
            if pending and pending[0] == i and is_sh:
                checks.append(Check(pending[0], pending[1], "\n".join(body)))
            elif pending and pending[0] == i:
                errors.append("line %d: verify line is followed by ```%s, not ```sh" % (pending[0], info))
            elif is_sh:
                errors.append("line %d: ```sh block without a verify line directly above it" % (i + 1))
            if pending and pending[0] != i:
                errors.append("line %d: verify line is not directly followed by a ```sh block" % pending[0])
            pending = None
            i = j + 1
            continue
        if pending and line.strip():
            errors.append("line %d: verify line is not directly followed by a ```sh block" % pending[0])
            pending = None
        elif pending and not line.strip():
            errors.append("line %d: blank line between the verify line and its block" % pending[0])
            pending = None
        i += 1
    if pending:
        errors.append("line %d: verify line is not followed by a ```sh block" % pending[0])
    if not checks and not errors:
        errors.append("the '%s' section holds no check" % HEADING)
    for check in checks:
        try:
            re.compile(check.regex, re.M)
        except re.error as exc:
            errors.append("line %d: the regular expression does not compile: %s" % (check.line, exc))
    return checks, errors


def logical_lines(block):
    """Join backslash continuations; drop blank and full-line comments."""
    joined, buf = [], ""
    for raw in block.split("\n"):
        if raw.rstrip().endswith("\\"):
            buf += raw.rstrip()[:-1] + " "
            continue
        buf += raw
        if buf.strip() and not buf.strip().startswith("#"):
            joined.append(buf.strip())
        buf = ""
    if buf.strip():
        joined.append(buf.strip())
    return joined


def split_pipeline(line):
    """Split on unquoted '|'; reject shell constructs outside of quotes."""
    stages, cur, quote, problems = [], "", None, []
    i = 0
    while i < len(line):
        ch = line[i]
        if quote == "'":
            cur += ch
            if ch == "'":
                quote = None
        elif quote == '"':
            cur += ch
            if ch == '"':
                quote = None
            elif ch in "$`":
                problems.append("expansion (%s) inside double quotes" % ch)
            elif ch == "\\":
                cur += line[i + 1:i + 2]
                i += 1
        else:
            if ch in "'\"":
                quote = ch
                cur += ch
            elif ch == "|":
                if line[i + 1:i + 2] == "|":
                    problems.append("'||' is not allowed")
                stages.append(cur)
                cur = ""
            elif ch in ";&<>`$()":
                problems.append("%r is not allowed outside quotes" % ch)
                cur += ch
            else:
                cur += ch
        i += 1
    if quote:
        problems.append("unterminated quote")
    stages.append(cur)
    return [s.strip() for s in stages], problems


def check_curl(args, api_prefix=API_PREFIX):
    """Return (problems, url count)."""
    problems, urls, i = [], [], 0
    while i < len(args):
        tok = args[i]
        value = None
        if tok.startswith("--"):
            name, eq, attached = tok.partition("=")
            if name in CURL_LONG_NOARG and not eq:
                i += 1
                continue
            if name not in CURL_LONG_ARG:
                problems.append("curl option %s is not allowed" % name)
                i += 1
                continue
            if eq:
                value = attached
            else:
                value = args[i + 1] if i + 1 < len(args) else None
                i += 1
            flag = name
        elif tok.startswith("-") and len(tok) > 1:
            flag = None
            for pos, ch in enumerate(tok[1:], 1):
                if ch in CURL_SHORT_NOARG:
                    continue
                if ch in CURL_SHORT_ARG:
                    flag = "-" + ch
                    rest = tok[pos + 1:]
                    if rest:
                        value = rest
                    else:
                        value = args[i + 1] if i + 1 < len(args) else None
                        i += 1
                    break
                problems.append("curl option -%s is not allowed" % ch)
                break
            if flag is None:
                i += 1
                continue
        else:
            urls.append(tok)
            i += 1
            continue
        if value is None:
            problems.append("curl option %s needs a value" % flag)
        elif flag in ("-X", "--request") and value.upper() not in ("GET", "HEAD"):
            problems.append("curl may only send GET or HEAD, not %s" % value)
        elif flag in ("-o", "--output") and value != "/dev/null":
            problems.append("curl may only write the body to stdout or /dev/null, not %s" % value)
        elif flag in ("-D", "--dump-header") and value != "-":
            problems.append("curl may only dump headers to stdout (-D -), not %s" % value)
        i += 1
    if len(urls) != 1:
        problems.append("each curl requests exactly one URL, found %d" % len(urls))
    for url in urls:
        if not (url == api_prefix or url.startswith(api_prefix + "/") or url.startswith(api_prefix + "?")):
            problems.append("curl may only request %s, not %s" % (api_prefix, url))
    return problems, len(urls)


def static_problems(check, api_prefix=API_PREFIX):
    problems, requests = [], 0
    lines = logical_lines(check.block)
    if not lines:
        return ["the block is empty"]
    for line in lines:
        stages, structural = split_pipeline(line)
        problems.extend(structural)
        for index, stage in enumerate(stages):
            try:
                words = shlex.split(stage)
            except ValueError as exc:
                problems.append("cannot parse %r: %s" % (stage, exc))
                continue
            if not words:
                problems.append("empty pipeline stage in %r" % line)
                continue
            if words[0] not in ALLOWED_COMMANDS:
                problems.append("command %r is not allowed (curl, jq, grep, head)" % words[0])
                continue
            if words[0] == "curl":
                curl_problems, count = check_curl(words[1:], api_prefix)
                problems.extend(curl_problems)
                requests += count
            elif words[0] == "head" and index > 0 and stages[0].startswith("curl"):
                sys.stderr.write("warning: line %d: 'curl | head' can fail under pipefail when the body is larger than the pipe buffer\n" % check.line)
    if requests == 0:
        problems.append("the block makes no request")
    if requests > MAX_REQUESTS:
        problems.append("the block makes %d requests; at most %d are allowed" % (requests, MAX_REQUESTS))
    return problems


def run(check, timeout):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/tmp"),
           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        proc = subprocess.run(["bash", "-euo", "pipefail", "-c", check.block], capture_output=True,
                              text=True, timeout=timeout, env=env)
        code, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        code, out, err = 124, "", "timed out after %ds" % timeout
    matched = bool(re.search(check.regex, out, re.M))
    return code, matched, out, err


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("readme", nargs="?", default="README.md")
    parser.add_argument("--run", action="store_true", help="execute each block against the live API")
    parser.add_argument("--json-out", help="write the per-check results as JSON")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--pause", type=float, default=1.0, help="seconds between blocks")
    parser.add_argument("--api-prefix", default=API_PREFIX,
                        help="the only URL prefix curl may request (default %(default)s; other values are for testing "
                             "against a local server)")
    args = parser.parse_args(argv)
    try:
        with open(args.readme, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print("CANNOT CHECK: %s" % exc)
        return 1

    checks, errors = parse(text)
    for check in checks:
        for problem in static_problems(check, args.api_prefix):
            errors.append("line %d: %s" % (check.line, problem))
    results = []
    if args.run and not errors:
        for index, check in enumerate(checks):
            if index:
                time.sleep(args.pause)
            code, matched, out, err = run(check, args.timeout)
            ok = code == 0 and matched
            results.append({"line": check.line, "regex": check.regex, "exitCode": code, "matched": matched,
                            "passed": ok, "stdout": out[-2000:], "stderr": err[-1000:]})
            print("%s line %d: exit %d, regex %s: %s" % ("ok  " if ok else "FAIL", check.line, code,
                                                          "found" if matched else "NOT found", check.regex))
            if not ok:
                errors.append("line %d: the command no longer proves its claim (exit %d, regex %s)"
                              % (check.line, code, "found" if matched else "not found"))
                sys.stdout.write("---- stdout (last 2000 characters)\n%s\n---- stderr\n%s\n----\n" % (out[-2000:], err[-1000:]))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({"checks": len(checks), "executed": bool(args.run and results), "errors": errors,
                       "results": results}, fh, indent=2)
            fh.write("\n")
    for error in errors:
        print("FAIL %s" % error)
    if errors:
        return 1
    what = "executed and matched" if args.run else "statically valid (not executed)"
    print("verify-it-yourself: ok - %d check(s) %s" % (len(checks), what))
    return 0


if __name__ == "__main__":
    sys.exit(main())
