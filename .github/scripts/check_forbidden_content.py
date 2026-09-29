#!/usr/bin/env python3
"""forbidden-content: no operational detail reaches the public repository.

Scans every tracked file (see repofiles.py) for:

  - IPv4 and IPv6 address literals, except the documentation ranges
    192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24 (RFC 5737) and
    2001:db8::/32 (RFC 3849);
  - absolute filesystem paths under the system directories a deployment lives
    in; published documentation describes an HTTP API and has no reason to
    name a path on the host that serves it;
  - shell access to a host: an ssh invocation, or a scp/rsync endpoint.

These rules are GENERAL, and deliberately so. An earlier version of this file
carried the literal names of this project's hosts, containers, internal paths
and non-public routes, so that it could match them exactly. That made the
check itself the most detailed inventory of internal names in the repository:
a reader learned from the scanner precisely what the scanner existed to keep
out of the repository. Obfuscating each literal ("x[y]z" matches "xyz") hid
them from the scan, not from the reader.

The exact-name check still exists. It runs BEFORE publication, in the private
repository where this documentation is written and where the names are already
known, and it is the gate that stops a specific host or route from reaching
this tree at all. What remains here is the general net: it catches a class of
mistake without describing this deployment to anyone.

No file is excluded, this one included.

Matches are printed masked (first three characters) with file:line:column, so
a leak found in a public log is located, not repeated.
"""

import argparse
import ipaddress
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repofiles  # noqa: E402

DOC_NETWORKS = [ipaddress.ip_network(n) for n in (
    "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24",  # RFC 5737
    "2001:db8::/32",                                       # RFC 3849
)]

IPV4 = re.compile(r"(?<![0-9A-Za-z.])(?:\d{1,3}\.){3}\d{1,3}(?![0-9A-Za-z]|\.\d)")
IPV6 = re.compile(r"(?<![0-9A-Za-z:.])[0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7}(?![0-9A-Za-z:])")

# System directories a service is deployed into. A public API reference names
# endpoints, not filesystems, so any of these is either an internal detail or a
# copied-in command that carries one.
SYSTEM_ROOTS = "root|etc|opt|srv|var/lib|var/log|var/www|home|mnt|proc|sys"

RULES = [
    ("host-path", re.compile(r"(?<![\w.-])/(?:%s)/[\w.-]" % SYSTEM_ROOTS)),
    # A shell command aimed at a host: a remote login carrying a user-at-host
    # target or an explicit port, or a copy command whose source or destination
    # is a remote endpoint. Requiring the user-at-host form (or the port flag)
    # is what separates a command from the word in a sentence: this file and the
    # authorship check both discuss SSH signatures in prose. The patterns below
    # are written so that they do not match their own description.
    ("host-access", re.compile(r"\bssh\s+(?:-\S+\s+)*[\w.-]+@[\w.-]+", re.I)),
    ("host-access", re.compile(r"\bssh\s+-p\s*\d+", re.I)),
    ("host-access", re.compile(r"\b(?:scp|rsync)\b[^\n]*\s[\w.-]+@[\w.-]+:", re.I)),
]


def mask(text):
    return text[:3] + "..." if len(text) > 3 else "***"


def address_hits(line):
    for match in IPV4.finditer(line):
        try:
            addr = ipaddress.ip_address(match.group(0))
        except ValueError:
            continue  # 999.1.1.1 and friends are not addresses
        if not any(addr in net for net in DOC_NETWORKS):
            yield "ipv4-literal", match
    for match in IPV6.finditer(line):
        text = match.group(0)
        if text.count(":") < 2 or not re.search(r"\d", text):
            continue
        try:
            addr = ipaddress.ip_address(text)
        except ValueError:
            continue  # times (12:30:45), MAC addresses, ratios
        if addr.version == 6 and not any(addr in net for net in DOC_NETWORKS):
            yield "ipv6-literal", match


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--walk", metavar="DIR", help="walk DIR instead of listing git-tracked files")
    args = parser.parse_args(argv)
    try:
        root, names = repofiles.list_files(args.walk)
    except repofiles.ReadError as exc:
        print("CANNOT CHECK: %s" % exc)
        return 1

    hits, unreadable = [], []
    files = lines = skipped = 0
    for name in names:
        try:
            text = repofiles.read_text(root, name)
        except repofiles.ReadError as exc:
            unreadable.append(str(exc))
            continue
        if text is None:
            skipped += 1
            continue
        files += 1
        for number, line in enumerate(text.splitlines(), 1):
            lines += 1
            found = list(address_hits(line))
            found += [(rule, m) for rule, rx in RULES for m in rx.finditer(line)]
            for rule, match in found:
                hits.append("%s:%d:%d: %s %s" % (name, number, match.start() + 1, rule, mask(match.group(0))))

    for hit in hits:
        print("FORBIDDEN %s" % hit)
    for problem in unreadable:
        print("CANNOT CHECK %s" % problem)
    if hits or unreadable:
        print("forbidden-content: %d finding(s), %d unreadable file(s)" % (len(hits), len(unreadable)))
        return 1
    if files == 0:
        print("CANNOT CHECK: no text file was read")
        return 1
    print("forbidden-content: ok - %d file(s), %d line(s) checked against %d rule(s) + address literals; %d binary file(s) skipped by extension"
          % (files, lines, len(RULES), skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
