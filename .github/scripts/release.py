#!/usr/bin/env python3
"""release: gates and notes for a tagged release.

check --tag vX.Y.Z[-pre] --spec SPEC.json [--readme README.md]
    The tag equals "v" + info.version of the spec, is a tag GitHub can carry,
    and the README names exactly this tag: the set of version strings in it
    (vX.Y.Z...) is {tag}. Set comparison, not "contains": a README that
    still names the previous release next to the new one fails.

notes --tag vX.Y.Z[-pre] [--changelog CHANGELOG.md]
    Prints the CHANGELOG.md section of the release (Keep a Changelog:
    "## [X.Y.Z-pre] - YYYY-MM-DD"). The section must exist, carry a date and
    have content.

verify-tag --tag vX.Y.Z[-pre] --repo OWNER/REPO
    Through the GitHub API: the tag is annotated, and GitHub verifies its
    signature (tag object verification.verified == true).
"""

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oas  # noqa: E402

VERSION_IN_TEXT = re.compile(r"\bv[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]*[0-9A-Za-z])?")
TAG_SHAPE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")


def cmd_check(args):
    errors = []
    if not TAG_SHAPE.match(args.tag):
        errors.append("tag %s is not vMAJOR.MINOR.PATCH[-pre-release]" % args.tag)
    doc = oas.load_json(args.spec)
    version = str((doc.get("info") or {}).get("version", ""))
    if args.tag != "v" + version:
        errors.append("tag %s != v%s (info.version of the spec)" % (args.tag, version))
    try:
        with open(args.readme, encoding="utf-8") as fh:
            named = sorted(set(VERSION_IN_TEXT.findall(fh.read())))
    except OSError as exc:
        named = None
        errors.append("cannot read %s: %s" % (args.readme, exc))
    if named is not None:
        if not named:
            errors.append("%s names no release tag; it must name %s" % (args.readme, args.tag))
        elif named != [args.tag]:
            errors.append("%s names [%s], the tag is %s" % (args.readme, ", ".join(named), args.tag))
    for error in errors:
        print("FAIL %s" % error)
    if errors:
        return 1
    print("release check: ok - %s = v(info.version) and the only version %s names" % (args.tag, args.readme))
    return 0


def section(changelog_text, version):
    lines = changelog_text.splitlines()
    head = re.compile(r"^## \[v?%s\](?P<rest>.*)$" % re.escape(version))
    for i, line in enumerate(lines):
        m = head.match(line)
        if not m:
            continue
        body = []
        for nxt in lines[i + 1:]:
            if nxt.startswith("## "):
                break
            body.append(nxt)
        return m.group("rest"), "\n".join(body).strip()
    return None, None


def cmd_notes(args):
    version = args.tag[1:] if args.tag.startswith("v") else args.tag
    try:
        with open(args.changelog, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print("FAIL cannot read %s: %s" % (args.changelog, exc), file=sys.stderr)
        return 1
    rest, body = section(text, version)
    if rest is None:
        print("FAIL %s has no '## [%s]' section" % (args.changelog, version), file=sys.stderr)
        return 1
    if not re.match(r"^ - \d{4}-\d{2}-\d{2}\s*$", rest):
        print("FAIL the '## [%s]' heading carries no release date (found %r)" % (version, rest.strip()), file=sys.stderr)
        return 1
    if not body:
        print("FAIL the '## [%s]' section is empty" % version, file=sys.stderr)
        return 1
    sys.stdout.write(body + "\n")
    return 0


def gh_api(path):
    out = subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def cmd_verify_tag(args):
    try:
        ref = gh_api("repos/%s/git/ref/tags/%s" % (args.repo, args.tag))
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print("FAIL cannot read tag %s of %s: %s" % (args.tag, args.repo, str(exc).strip()[:200]))
        return 1
    obj = ref.get("object") or {}
    if obj.get("type") != "tag":
        print("FAIL %s is a lightweight tag (%s); releases need an annotated, signed tag" % (args.tag, obj.get("type")))
        return 1
    tag = gh_api("repos/%s/git/tags/%s" % (args.repo, obj.get("sha")))
    verification = tag.get("verification") or {}
    if verification.get("verified") is not True:
        print("FAIL GitHub does not verify the signature of tag %s (reason: %s)" % (args.tag, verification.get("reason")))
        return 1
    print("release verify-tag: ok - %s is annotated and its signature is verified by GitHub" % args.tag)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")
    c = sub.add_parser("check")
    c.add_argument("--tag", required=True)
    c.add_argument("--spec", required=True)
    c.add_argument("--readme", default="README.md")
    n = sub.add_parser("notes")
    n.add_argument("--tag", required=True)
    n.add_argument("--changelog", default="CHANGELOG.md")
    v = sub.add_parser("verify-tag")
    v.add_argument("--tag", required=True)
    v.add_argument("--repo", required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "check":
            return cmd_check(args)
        if args.cmd == "notes":
            return cmd_notes(args)
        if args.cmd == "verify-tag":
            return cmd_verify_tag(args)
    except oas.CannotCheck as exc:
        print("CANNOT CHECK: %s" % exc)
        return 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
