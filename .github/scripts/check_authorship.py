#!/usr/bin/env python3
"""authorship: every commit is the maintainer's, signed, with no co-author.

For each commit in the range:
  - the author is exactly `zim.one <zimone91@gmail.com>`, name and address;
  - the committer is exactly the same identity: main moves by fast-forward to
    the SHA the maintainer signed, so no commit is made on github.com and
    neither GitHub's web-flow identity nor a noreply address is accepted;
  - the commit object carries a signature (a gpgsig header);
  - the message has no Co-authored-by trailer (any case).

Presence of a signature is read from the commit object itself rather than
from `git log --format=%G?`: without gpg.ssh.allowedSignersFile, git reports
an SSH-signed commit as "N" (no signature), which would fail every commit the
maintainer signs with an SSH key. Validity is GitHub's call: with
--github-repo, each commit in the range (the newest --github-max of them,
default 100, to bound API calls on whole-history runs) must also have
commit.verification.verified == true in the GitHub API (the maintainer's
registered signing key).

Range: --range A..B, or a single revision for its whole history. In GitHub
Actions, --from-event derives it from the event: pull_request -> base..head;
push -> before..after (whole history of `after` when `before` is unknown);
anything else -> the whole history of HEAD.
"""

import argparse
import json
import os
import re
import subprocess
import sys

# The one identity this repository is written under (owner's decision, 26.09).
MAINTAINER = ("zim.one", "zimone91@gmail.com")
TRAILER = re.compile(r"^\s*co-authored-by\s*:", re.I | re.M)
ZERO = "0" * 40


def git(*args):
    return subprocess.run(["git"] + list(args), check=True, capture_output=True, text=True).stdout


def commit_exists(rev):
    return subprocess.run(["git", "cat-file", "-e", rev + "^{commit}"], capture_output=True).returncode == 0


def range_from_event():
    event = os.environ.get("EVENT_NAME", "")
    if event == "pull_request":
        base, head = os.environ.get("BASE_SHA", ""), os.environ.get("HEAD_SHA", "")
        if base and head:
            return "%s..%s" % (base, head)
    if event == "push":
        before, after = os.environ.get("BEFORE_SHA", ""), os.environ.get("AFTER_SHA", "")
        if after and before and before != ZERO and commit_exists(before):
            return "%s..%s" % (before, after)
        if after:
            return after
    return "HEAD"


def commits(rev_range):
    shas = git("rev-list", "--reverse", rev_range).split()
    for sha in shas:
        raw = git("cat-file", "commit", sha)
        header, _, message = raw.partition("\n\n")
        signed = any(line.startswith(("gpgsig ", "gpgsig-sha256 ")) for line in header.split("\n"))
        # Name and address both: a commit under someone else's name with the maintainer's
        # address is still someone else's commit.
        an, ae, cn, ce = git("log", "-1", "--format=%an%x00%ae%x00%cn%x00%ce", sha).rstrip("\n").split("\0")
        yield sha, (an, ae), (cn, ce), signed, message


def github_verification(repo, sha):
    try:
        out = subprocess.run(["gh", "api", "repos/%s/commits/%s" % (repo, sha), "--jq", ".commit.verification"],
                             check=True, capture_output=True, text=True).stdout
        return json.loads(out)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        return {"verified": False, "reason": "api-error: %s" % str(exc).strip()[:200]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--range", help="A..B, or one revision for its whole history")
    group.add_argument("--from-event", action="store_true", help="derive the range from the GitHub event (env)")
    parser.add_argument("--github-repo", help="OWNER/REPO: also require GitHub's signature verification")
    parser.add_argument("--github-max", type=int, default=100,
                        help="ask GitHub about the newest N commits of the range only (default 100); "
                             "the local checks always cover every commit")
    args = parser.parse_args(argv)

    rev_range = range_from_event() if args.from_event else args.range
    try:
        found = list(commits(rev_range))
    except subprocess.CalledProcessError as exc:
        print("CANNOT CHECK: git failed for range %s: %s" % (rev_range, (exc.stderr or "").strip()))
        return 1
    if not found:
        print("CANNOT CHECK: no commit in range %s" % rev_range)
        return 1

    errors = []
    ask_github = {c[0] for c in found[-args.github_max:]} if args.github_repo and args.github_max > 0 else set()
    expected = "%s <%s>" % MAINTAINER
    for sha, author, committer, signed, message in found:
        short = sha[:12]
        if author != MAINTAINER:
            errors.append("%s: author %s <%s> is not %s" % (short, author[0], author[1], expected))
        if committer != MAINTAINER:
            errors.append("%s: committer %s <%s> is not %s" % (short, committer[0], committer[1], expected))
        if not signed:
            errors.append("%s: commit is not signed" % short)
        if TRAILER.search(message):
            errors.append("%s: message carries a Co-authored-by trailer" % short)
        if sha in ask_github:
            verification = github_verification(args.github_repo, sha)
            if verification.get("verified") is not True:
                errors.append("%s: GitHub does not verify the signature (reason: %s)" % (short, verification.get("reason")))
    for error in errors:
        print("FAIL %s" % error)
    if ask_github:
        what = "local checks on all, GitHub verification on the newest %d" % len(ask_github)
    else:
        what = "local checks only"
    if errors:
        print("authorship: %d problem(s) in %d commit(s) of %s (%s)" % (len(errors), len(found), rev_range, what))
        return 1
    print("authorship: ok - %d commit(s) in %s (%s)" % (len(found), rev_range, what))
    return 0


if __name__ == "__main__":
    sys.exit(main())
