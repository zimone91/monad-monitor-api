#!/usr/bin/env python3
"""contract-live: the live API still answers the way the spec says.

requests --spec SPEC.json --out DIR [--base URL]
    One GET per documented operation with a JSON 200 response, sent to the
    request its live example was captured with (the command in
    examples.live.description, re-based onto the /v1 base URL), and one HEAD
    per operation without one (the logo). Requests are sequential, one second
    apart. Each JSON answer must be 200 application/json, carry every response
    header the spec documents for the 200 response, declare every key it holds in the
    schema (undocumented-field check), and be valid against the schema:
    the answers are substituted for examples.live.value in a copy of the
    spec, which Spectral validates with oas3-valid-media-example at error
    severity (the same validator the examples job uses). A HEAD answer must
    be 200 with a documented media type (and the documented headers), or a
    documented 404.

drift --spec-yaml openapi/openapi.yaml --out DIR [--base URL]
    Fetches <base>/openapi.json, requires only OpenAPI root fields in it,
    and requires `oasdiff diff --fail-on-diff --exclude-elements examples`
    against the repository's spec to report no difference in the contract.
    Examples are excluded because the served document has none: they are
    captured responses and live in examples/ and in openapi.yaml, so that
    re-capturing them is a documentation change and not a deployment.

summarize --out DIR --live OUTCOME --drift OUTCOME --verify OUTCOME
    Writes DIR/contract.json (result, UTC time, per-part detail) and
    DIR/badges/contract.json ("passed <date>" or "failed <date>").

Standard library only; Spectral and oasdiff are the pinned CI tools.
"""

import argparse
import copy
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oas  # noqa: E402
from check_examples import command_path  # noqa: E402

USER_AGENT = "monad-monitor-api-contract-live (+https://github.com/zimone91/monad-monitor-api)"
OAS_ROOT = {"openapi", "info", "jsonSchemaDialect", "servers", "paths", "webhooks", "components",
            "security", "tags", "externalDocs"}
HERE = os.path.dirname(os.path.abspath(__file__))


def fetch(url, method="GET", timeout=30):
    req = urllib.request.Request(url, method=method, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json" if method == "GET" else "*/*"})
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, headers, body = resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as exc:
        status, headers, body = exc.code, exc.headers, exc.read()
    except (urllib.error.URLError, OSError) as exc:
        return None, {}, b"", int((time.time() - started) * 1000), str(exc)
    return status, headers, body, int((time.time() - started) * 1000), None


def param_values(doc):
    """Path parameter values used by the live examples, e.g. {'id': '109'}."""
    values = {}
    for _method, path, op in oas.operations(doc):
        media = oas.json_media(doc, op)
        live = ((media or {}).get("examples") or {}).get("live") or {}
        try:
            _c, _n, req_path, _q = command_path(live.get("description") or "")
        except ValueError:
            continue
        names = re.findall(r"\{([^}/]+)\}", path)
        match = oas.path_regex(path).match(req_path)
        if names and match:
            pieces = re.split(r"(\{[^}/]+\})", path)
            rx = "^" + "".join("(?P<p%d>[^/?#]+)" % i if p.startswith("{") else re.escape(p)
                                for i, p in enumerate(pieces)) + "$"
            m = re.match(rx, req_path)
            for i, piece in enumerate(pieces):
                if piece.startswith("{") and m:
                    values.setdefault(piece[1:-1], m.group("p%d" % i))
    return values


def concrete_path(doc, path, op, known):
    def value(name):
        for param in op.get("parameters") or []:
            param = oas.deref(doc, param)
            if param.get("in") == "path" and param.get("name") == name and "example" in param:
                return str(param["example"])
        return known.get(name)
    out = path
    for name in re.findall(r"\{([^}/]+)\}", path):
        val = value(name)
        if val is None:
            return None
        out = out.replace("{%s}" % name, val)
    return out


def documented_headers(doc, op):
    """Every header the spec documents for the 200 response. The spec does
    not mark them `required`, but it documents them as sent on every 200, so
    a missing one is drift."""
    resp = oas.response(doc, op) or {}
    return sorted(resp.get("headers") or {})


def cmd_requests(args):
    doc = oas.load_json(args.spec)
    live_doc = copy.deepcopy(doc)
    known = param_values(doc)
    results, errors, op_errors = [], [], []  # errors: not tied to one answer
    failed_ops = 0
    first = True
    for method, path, op in oas.operations(doc):
        if method != "get":
            continue
        op_id = op.get("operationId", "%s %s" % (method.upper(), path))
        media = oas.json_media(doc, op)
        if media is not None:
            live = (media.get("examples") or {}).get("live") or {}
            try:
                _c, _n, req_path, query = command_path(live.get("description") or "")
            except ValueError as exc:
                errors.append("%s: cannot derive the request from examples.live.description: %s" % (op_id, exc))
                continue
            verb = "GET"
            url = args.base + req_path + ("?" + query if query else "")
        else:
            concrete = concrete_path(doc, path, op, known)
            if concrete is None:
                errors.append("%s: no example value for a path parameter of %s" % (op_id, path))
                continue
            verb, url = "HEAD", args.base + concrete
        if not first:
            time.sleep(args.pause)
        first = False
        status, headers, body, ms, failure = fetch(url, verb)
        entry = {"operationId": op_id, "method": verb, "url": url, "status": status, "ms": ms, "problems": []}
        problems = entry["problems"]
        if failure:
            problems.append("request failed: %s" % failure)
        elif media is not None:
            ctype = headers.get("Content-Type", "")
            if status != 200:
                problems.append("status %s, expected 200" % status)
            if not ctype.lower().startswith("application/json"):
                problems.append("Content-Type %r, expected application/json" % ctype)
            for name in documented_headers(doc, op):
                if headers.get(name) is None:
                    problems.append("documented response header %s is missing" % name)
            try:
                payload = json.loads(body.decode("utf-8"))
            except ValueError as exc:
                problems.append("body is not JSON: %s" % exc)
                payload = None
            if payload is not None and status == 200:
                try:
                    for problem in oas.dedupe_paths(oas.undocumented(doc, payload, media.get("schema") or {})):
                        problems.append("undocumented field %s" % problem)
                except oas.CannotCheck as exc:
                    problems.append("CANNOT CHECK undocumented fields: %s" % exc)
                target = oas.json_media(live_doc, oas.deref(live_doc, live_doc["paths"][path])[method])
                target.setdefault("examples", {}).setdefault("live", {})["value"] = payload
                entry["checkedAgainstSchema"] = True
        else:
            documented = {str(code) for code in (op.get("responses") or {})}
            acceptable = documented & {"200", "404"}
            if str(status) not in acceptable:
                problems.append("status %s, expected one of %s" % (status, ", ".join(sorted(acceptable)) or "200"))
            elif status == 200:
                ctype = headers.get("Content-Type", "").split(";")[0].strip().lower()
                media_types = [m.lower() for m in ((oas.response(doc, op) or {}).get("content") or {})]
                if ctype not in media_types:
                    problems.append("Content-Type %r is not documented (%s)" % (ctype, ", ".join(media_types)))
                for name in documented_headers(doc, op):
                    if headers.get(name) is None:
                        problems.append("documented response header %s is missing" % name)
        print("%s %-4s %s -> %s in %d ms%s" % ("ok  " if not problems else "FAIL", verb, url, status, ms,
                                               "".join("\n     - " + p for p in problems)))
        results.append(entry)
        failed_ops += 1 if problems else 0
        op_errors.extend("%s: %s" % (op_id, p) for p in problems)

    if not results:
        errors.append("no request was made: nothing was checked")
    os.makedirs(args.out, exist_ok=True)
    live_spec = os.path.join(args.out, "live-spec.json")
    with open(live_spec, "w", encoding="utf-8") as fh:
        json.dump(live_doc, fh)

    # Schema validation of the live bodies with the pinned Spectral.
    schema_ok = None
    if any(r.get("checkedAgainstSchema") for r in results):
        proc = subprocess.run([args.spectral, "lint", live_spec, "--ruleset", args.ruleset,
                               "--fail-severity", "error", "--format", "json", "--quiet"],
                              capture_output=True, text=True)
        try:
            findings = json.loads(proc.stdout or "[]")
        except ValueError:
            findings = None
        if findings is None or proc.returncode not in (0, 1):
            errors.append("Spectral did not run cleanly (exit %d): %s" % (proc.returncode, (proc.stderr or proc.stdout)[:500]))
            schema_ok = False
        else:
            bad = [f for f in findings if f.get("severity") == 0]
            for finding in bad:
                where = "/".join(str(p) for p in finding.get("path", []))
                errors.append("schema: %s (%s) at %s" % (finding.get("message"), finding.get("code"), where))
            schema_ok = not bad and proc.returncode == 0
            print("%s schema validation of %d live body(ies) with Spectral: %d error(s)"
                  % ("ok  " if schema_ok else "FAIL", sum(1 for r in results if r.get("checkedAgainstSchema")), len(bad)))
    with open(os.path.join(args.out, "live-results.json"), "w", encoding="utf-8") as fh:
        json.dump({"base": args.base, "results": results, "schemaValid": schema_ok,
                   "errors": op_errors + errors}, fh, indent=2)
        fh.write("\n")
    # per-operation problems were printed under each request; print the others here
    for error in errors:
        print("FAIL %s" % error)
    if errors or op_errors:
        print("contract-live requests: %d problem(s); %d of %d operation(s) did not answer as documented"
              % (len(errors) + len(op_errors), failed_ops, len(results)))
        return 1
    print("contract-live requests: ok - %d operation(s) answered as documented" % len(results))
    return 0


def cmd_drift(args):
    url = args.base + "/openapi.json"
    status, _headers, body, ms, failure = fetch(url)
    os.makedirs(args.out, exist_ok=True)
    errors = []
    served = os.path.join(args.out, "served-openapi.json")
    if failure or status != 200:
        errors.append("GET %s -> %s" % (url, failure or status))
    else:
        try:
            served_doc = json.loads(body.decode("utf-8"))
            with open(served, "w", encoding="utf-8") as fh:
                json.dump(served_doc, fh, indent=2)
            extra = sorted(k for k in served_doc if k not in OAS_ROOT and not k.startswith("x-"))
            if extra:
                errors.append("served document has non-OpenAPI root field(s): %s" % ", ".join(extra))
        except ValueError as exc:
            errors.append("served document is not JSON: %s" % exc)
    diff_output = ""
    if not errors:
        # The CONTRACT is compared, not the examples. The served document carries no
        # examples at all (the API strips them), while openapi.yaml publishes them
        # alongside the same contract: they are captured responses, and a document the
        # service serves about itself must not depend on the service's own answers. So
        # `--exclude-elements examples` here is not a relaxation — it is the comparison
        # this check was always meant to make. That no example leaks INTO the served
        # document is checked separately, next to the document itself.
        proc = subprocess.run([args.oasdiff, "diff", args.spec_yaml, served, "--fail-on-diff",
                               "--exclude-elements", "examples",
                               "--allow-external-refs=false", "--format", "text"],
                              capture_output=True, text=True)
        diff_output = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0:
            errors.append("oasdiff reports a difference between %s and %s (exit %d)" % (args.spec_yaml, url, proc.returncode))
        print(diff_output or "(oasdiff printed nothing)")
    with open(os.path.join(args.out, "drift-results.json"), "w", encoding="utf-8") as fh:
        json.dump({"url": url, "status": status, "ms": ms, "diff": diff_output[:20000], "errors": errors}, fh, indent=2)
        fh.write("\n")
    for error in errors:
        print("FAIL %s" % error)
    if errors:
        return 1
    print("contract-live drift: ok - %s and %s describe the same contract" % (url, args.spec_yaml))
    return 0


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def cmd_summarize(args):
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    parts = {"requests": args.live, "drift": args.drift, "verify": args.verify}
    passed = all(v == "success" for v in parts.values())
    contract = {
        "result": "passed" if passed else "failed",
        "checkedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "api": args.base,
        "parts": parts,
        "requests": read_json(os.path.join(args.out, "live-results.json")),
        "drift": read_json(os.path.join(args.out, "drift-results.json")),
        "verifyItYourself": read_json(args.verify_json) if args.verify_json else None,
        "run": os.environ.get("RUN_URL", ""),
        "commit": os.environ.get("GITHUB_SHA", ""),
    }
    badge = {"schemaVersion": 1, "label": "contract",
             "message": "%s %s" % ("passed" if passed else "failed", now.strftime("%Y-%m-%d")),
             "color": "brightgreen" if passed else "red"}
    os.makedirs(os.path.join(args.out, "badges"), exist_ok=True)
    with open(os.path.join(args.out, "contract.json"), "w", encoding="utf-8") as fh:
        json.dump(contract, fh, indent=2)
        fh.write("\n")
    with open(os.path.join(args.out, "badges", "contract.json"), "w", encoding="utf-8") as fh:
        json.dump(badge, fh)
        fh.write("\n")
    print("contract: %s at %s (%s)" % (contract["result"], contract["checkedAt"],
                                      ", ".join("%s=%s" % kv for kv in parts.items())))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")
    r = sub.add_parser("requests")
    r.add_argument("--spec", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--base", default=oas.API_BASE)
    r.add_argument("--pause", type=float, default=1.0)
    r.add_argument("--spectral", default="spectral")
    r.add_argument("--ruleset", default=os.path.join(HERE, "examples.spectral.yaml"))
    d = sub.add_parser("drift")
    d.add_argument("--spec-yaml", default="openapi/openapi.yaml")
    d.add_argument("--out", required=True)
    d.add_argument("--base", default=oas.API_BASE)
    d.add_argument("--oasdiff", default="oasdiff")
    s = sub.add_parser("summarize")
    s.add_argument("--out", required=True)
    s.add_argument("--base", default=oas.API_BASE)
    s.add_argument("--live", required=True)
    s.add_argument("--drift", required=True)
    s.add_argument("--verify", required=True)
    s.add_argument("--verify-json")
    args = parser.parse_args(argv)
    args.base = getattr(args, "base", oas.API_BASE).rstrip("/")
    try:
        if args.cmd == "requests":
            return cmd_requests(args)
        if args.cmd == "drift":
            return cmd_drift(args)
        if args.cmd == "summarize":
            return cmd_summarize(args)
    except oas.CannotCheck as exc:
        print("CANNOT CHECK: %s" % exc)
        return 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
