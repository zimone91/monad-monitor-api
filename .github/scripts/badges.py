#!/usr/bin/env python3
"""badges: README badge rules, and the numbers behind the live badges.

verify-readme README.md
    Every image in the README must be a live badge from an allowed source:
      - the ci.yml workflow badge (any workflow file that exists);
      - img.shields.io/endpoint?url=https://zimone91.github.io/monad-monitor-api/badges/<name>.json
        with <name> one of: checks, contract, openapi, status, endpoints, examples;
      - img.shields.io/github/{v/release,release,license,check-runs}/zimone91/monad-monitor-api...;
        check-runs needs nameFilter=<a job name that exists in .github/workflows>;
      - img.shields.io/badge/dynamic/json?url=https://api.zim.one/v1/health/indexer&query=$.status
        (the only /badge/ path allowed: it reads the API);
      - api.scorecard.dev/projects/github.com/zimone91/monad-monitor-api/badge.
    A static img.shields.io/badge/<text> badge, or any other image, fails.

write --spec SPEC.json --out DIR
    Writes shields "endpoint" JSON files computed from this run:
      checks.json     K/K passing   (needs results from NEEDS_JSON, plus the
                                     README badge rules via README_OUTCOME)
      endpoints.json  N documented  (operations under `paths`)
      examples.json   M validated   (examples job output, or "failing")
      openapi.json    3.1.x valid   (the spec's `openapi`, valid when spec-lint passed)
      status.json     beta          (the pre-release label of info.version)
    and DIR/../checks-detail.json with the result of each job.
"""

import argparse
import glob
import html
import json
import os
import re
import sys
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oas  # noqa: E402

REPO = "zimone91/monad-monitor-api"
PAGES = "https://zimone91.github.io/monad-monitor-api/badges/"
ENDPOINT_BADGES = ("checks", "contract", "openapi", "status", "endpoints", "examples")
GITHUB_KINDS = ("v/release/", "release/", "license/", "check-runs/")
DYNAMIC_URL = "https://api.zim.one/v1/health/indexer"
SCORECARD = "https://api.scorecard.dev/projects/github.com/%s/badge" % REPO

MD_INLINE = re.compile(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
MD_REF_USE = re.compile(r"!\[([^\]]*)\]\[([^\]]*)\]")
MD_REF_DEF = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*<?(\S+?)>?(?:\s+.*)?$", re.M)
HTML_IMG = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)


def job_names(workflow_dir):
    """Check-run names of every job: the job's `name:` if set, else its id.
    Jobs that call a reusable workflow in this repository also contribute
    '<caller> / <callee job>' names. Parsed with indentation rules that the
    workflow files follow (two spaces per level); zero jobs is an error."""
    per_file = {}
    for path in sorted(glob.glob(os.path.join(workflow_dir, "*.yml")) + glob.glob(os.path.join(workflow_dir, "*.yaml"))):
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        jobs, current, in_jobs = {}, None, False
        for line in lines:
            if re.match(r"^jobs:\s*(#.*)?$", line):
                in_jobs = True
                continue
            if in_jobs and re.match(r"^\S", line):
                in_jobs = False
            if not in_jobs:
                continue
            m = re.match(r"^  ([A-Za-z_][A-Za-z0-9_-]*):\s*(#.*)?$", line)
            if m:
                current = m.group(1)
                jobs[current] = {"name": None, "uses": None}
                continue
            m = re.match(r"^    name:\s*(.+?)\s*(#.*)?$", line)
            if m and current:
                jobs[current]["name"] = m.group(1).strip("'\"")
            m = re.match(r"^    uses:\s*\./\.github/workflows/(\S+?)\s*(#.*)?$", line)
            if m and current:
                jobs[current]["uses"] = m.group(1)
        per_file[os.path.basename(path)] = jobs
    names = set()
    for jobs in per_file.values():
        for job_id, info in jobs.items():
            display = info["name"] or job_id
            names.add(display)
            if info["uses"] and info["uses"] in per_file:
                for sub_id, sub in per_file[info["uses"]].items():
                    names.add("%s / %s" % (display, sub["name"] or sub_id))
    return set(per_file), names


def images(text):
    urls = [m.group(1) for m in MD_INLINE.finditer(text)]
    defs = {m.group(1).strip().lower(): m.group(2) for m in MD_REF_DEF.finditer(text)}
    for m in MD_REF_USE.finditer(text):
        label = (m.group(2) or m.group(1)).strip().lower()
        urls.append(defs.get(label, "<undefined reference [%s]>" % label))
    for m in HTML_IMG.finditer(text):
        urls.append(m.group(1).strip("'\""))
    return [html.unescape(u) for u in urls]


def judge(url, workflows, jobs):
    """Return None if the image is an allowed live badge, else the reason."""
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    host, path = parts.netloc.lower(), parts.path
    if parts.scheme != "https":
        return "not an https URL"
    if host == "github.com":
        m = re.match(r"^/%s/actions/workflows/([^/]+)/badge\.svg$" % re.escape(REPO), path)
        if not m:
            return "not this repository's workflow badge"
        if m.group(1) not in workflows:
            return "workflow %s does not exist in .github/workflows" % m.group(1)
        return None
    if host == "api.scorecard.dev":
        return None if url.split("?")[0] == SCORECARD else "not this repository's Scorecard badge"
    if host != "img.shields.io":
        return "image host %s is not an allowed badge source" % host
    if path == "/endpoint":
        target = (query.get("url") or [""])[0]
        if not target.startswith(PAGES) or not target.endswith(".json"):
            return "endpoint badge must read %s<name>.json" % PAGES
        name = target[len(PAGES):-len(".json")]
        return None if name in ENDPOINT_BADGES else "endpoint badge %r is not one of %s" % (name, ", ".join(ENDPOINT_BADGES))
    if path.startswith("/github/"):
        rest = path[len("/github/"):]
        kind = next((k for k in GITHUB_KINDS if rest.startswith(k)), None)
        if not kind:
            return "shields github badge %s is not release, license or check-runs" % rest.split("/")[0]
        if not rest[len(kind):].startswith(REPO):
            return "shields github badge is not about %s" % REPO
        if kind == "check-runs/":
            names = query.get("nameFilter")
            if not names:
                return "check-runs badge without nameFilter"
            if names[0] not in jobs:
                return "nameFilter=%r is not a job name in .github/workflows" % names[0]
        return None
    if path == "/badge/dynamic/json":
        if (query.get("url") or [""])[0] != DYNAMIC_URL or (query.get("query") or [""])[0] != "$.status":
            return "the only dynamic badge allowed reads $.status of %s" % DYNAMIC_URL
        return None
    if path.startswith("/badge/"):
        return "static badge: nothing checks the text it shows"
    return "shields path %s is not an allowed live badge" % path


def verify_readme(readme, workflow_dir):
    try:
        with open(readme, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print("CANNOT CHECK: %s" % exc)
        return 1
    workflows, jobs = job_names(workflow_dir)
    if not jobs:
        print("CANNOT CHECK: no job found in %s" % workflow_dir)
        return 1
    found = images(text)
    if not found:
        print("CANNOT CHECK: %s has no image: the badge rows are missing or were not recognized" % readme)
        return 1
    errors = []
    for url in found:
        reason = judge(url, workflows, jobs)
        print("%s %s%s" % ("ok  " if reason is None else "FAIL", url, "" if reason is None else "  <- " + reason))
        if reason:
            errors.append(url)
    if errors:
        print("readme-badges: %d of %d image(s) break the badge rules" % (len(errors), len(found)))
        return 1
    print("readme-badges: ok - %d badge(s), all live; %d job name(s) known" % (len(found), len(jobs)))
    return 0


def endpoint(label, message, color):
    return {"schemaVersion": 1, "label": label, "message": message, "color": color}


def status_of(version):
    m = re.match(r"^\d+\.\d+\.\d+(?:-([0-9A-Za-z.-]+))?(?:\+.*)?$", version or "")
    if not m:
        return None
    pre = m.group(1)
    if not pre:
        return "stable"
    word = re.match(r"[A-Za-z]+", pre)
    return word.group(0).lower() if word else "pre-release"


def write(spec_path, out_dir):
    try:
        doc = oas.load_json(spec_path)
    except oas.CannotCheck as exc:
        print("CANNOT CHECK: %s" % exc)
        return 1
    try:
        needs = json.loads(os.environ.get("NEEDS_JSON") or "")
    except ValueError:
        print("CANNOT CHECK: NEEDS_JSON is not set to toJSON(needs)")
        return 1
    results = {job: (info or {}).get("result", "") for job, info in needs.items()}
    readme = os.environ.get("README_OUTCOME", "")
    if readme:
        results["readme-badges"] = readme
    ran = {job: r for job, r in results.items() if r not in ("skipped", "")}
    passed = sum(1 for r in ran.values() if r == "success")
    if not ran:
        print("CANNOT CHECK: no job result to count")
        return 1

    count = sum(1 for _ in oas.operations(doc))
    ex_result = results.get("examples")
    validated = ((needs.get("examples") or {}).get("outputs") or {}).get("validated", "")
    openapi = str(doc.get("openapi", "?"))
    status = status_of(str((doc.get("info") or {}).get("version", "")))
    spec_ok = results.get("spec-lint") == "success"

    badges = {
        "checks": endpoint("checks", "%d/%d passing" % (passed, len(ran)), "brightgreen" if passed == len(ran) else "red"),
        "endpoints": endpoint("endpoints", "%d documented" % count, "blue" if count else "red"),
        "examples": (endpoint("examples", "%s validated" % validated, "brightgreen")
                     if ex_result == "success" and validated.isdigit() else endpoint("examples", "failing", "red")),
        "openapi": endpoint("OpenAPI", "%s %s" % (openapi, "valid" if spec_ok else "invalid"), "brightgreen" if spec_ok else "red"),
        "status": (endpoint("status", status, "brightgreen" if status == "stable" else "orange")
                   if status else endpoint("status", "unknown version", "red")),
    }
    os.makedirs(out_dir, exist_ok=True)
    for name, body in badges.items():
        with open(os.path.join(out_dir, name + ".json"), "w", encoding="utf-8") as fh:
            json.dump(body, fh)
            fh.write("\n")
        print("%-10s %s: %s (%s)" % (name + ".json", body["label"], body["message"], body["color"]))
    detail = {"results": results, "passed": passed, "ran": len(ran),
              "run": os.environ.get("RUN_URL", ""), "commit": os.environ.get("GITHUB_SHA", "")}
    with open(os.path.join(os.path.dirname(os.path.abspath(out_dir)), "checks-detail.json"), "w", encoding="utf-8") as fh:
        json.dump(detail, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")
    v = sub.add_parser("verify-readme")
    v.add_argument("readme", nargs="?", default="README.md")
    v.add_argument("--workflows", default=".github/workflows")
    w = sub.add_parser("write")
    w.add_argument("--spec", required=True)
    w.add_argument("--out", required=True, help="directory for the badge JSON files")
    args = parser.parse_args(argv)
    if args.cmd == "verify-readme":
        return verify_readme(args.readme, args.workflows)
    if args.cmd == "write":
        return write(args.spec, args.out)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
