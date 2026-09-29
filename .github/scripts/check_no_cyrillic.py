#!/usr/bin/env python3
"""no-cyrillic: any Cyrillic character in any tracked file is an error.

Everything in this repository is English. The ranges below are the Unicode
Cyrillic blocks (written as escapes, so this file passes its own check and is
not excluded from it). Files that are not UTF-8 text fail the check instead
of being skipped, except known binary formats (see repofiles.py). The verdict
names how many files and lines were read.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repofiles  # noqa: E402

CYRILLIC = re.compile(
    "[\u0400-\u052f"          # Cyrillic, Cyrillic Supplement
    "\u1c80-\u1c8f"           # Cyrillic Extended-C
    "\u1d2b\u1d78"            # Cyrillic letters in Phonetic Extensions
    "\u2de0-\u2dff"           # Cyrillic Extended-A
    "\ua640-\ua69f"           # Cyrillic Extended-B
    "\U0001e030-\U0001e08f]"  # Cyrillic Extended-D
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
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
            for match in CYRILLIC.finditer(line):
                hits.append("%s:%d:%d: U+%04X" % (name, number, match.start() + 1, ord(match.group(0))))

    for hit in hits:
        print("CYRILLIC %s" % hit)
    for problem in unreadable:
        print("CANNOT CHECK %s" % problem)
    if hits or unreadable:
        print("no-cyrillic: %d Cyrillic character(s), %d unreadable file(s)" % (len(hits), len(unreadable)))
        return 1
    if files == 0:
        print("CANNOT CHECK: no text file was read")
        return 1
    print("no-cyrillic: ok - %d file(s), %d line(s) checked; %d binary file(s) skipped by extension" % (files, lines, skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
