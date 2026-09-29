#!/usr/bin/env python3
"""site-page: the published page loads nothing from another host (SPEC 3.6).

localize --page INDEX.html --bundle-url URL --bundle-file FILE
         --asset-url URL2 --asset-local NAME2
    `redocly build-docs` points the page at Redoc's bundle on a CDN. The
    bundle is served next to the page instead, as FILE: the one <script src>
    must be exactly URL, and it is rewritten to FILE's name. The bundle
    itself loads one thing from another host at run time, the logo of its
    sidebar credit (URL2); that URL, which must occur exactly once, is
    replaced by NAME2, served next to the page. The page's integrity
    attribute is rewritten to the edited bundle. Then a
    Content-Security-Policy <meta> is inserted right after <meta charset>,
    before any script, with the sha256 of every inline script. The policy
    names no host at all.

check SITE_DIR
    Fails (exit 1) when SITE_DIR/index.html
      - references another host from script, link, img and the other
        resource-loading elements, or from url() / @import in its CSS
        (which covers @font-face);
      - has no Content-Security-Policy <meta>, has more than one, or has one
        placed after the first script;
      - has a policy whose default-src is not 'none', or that names a host,
        a scheme other than data: and blob:, or a keyword this page does not
        need;
      - has an inline script whose hash the policy does not list, or a local
        script or stylesheet that is missing from SITE_DIR.
    A check that finds nothing to check fails too: no page, or no script.
"""

import argparse
import base64
import hashlib
import html.parser
import os
import re
import sys

# What Redoc needs, measured in a browser (zero CSP reports): its bundle and
# the page's inline script from this origin; styles injected at run time
# (styled-components), so 'unsafe-inline' for styles; data: images in its
# CSS; its search index runs in a Worker created from a blob: URL.
POLICY = (
    "default-src 'none'; script-src 'self' {hashes}; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; worker-src blob:; "
    "base-uri 'none'; form-action 'none'"
)
ALLOWED_SOURCES = re.compile(r"^(?:'self'|'none'|'unsafe-inline'|'sha256-[A-Za-z0-9+/]+={0,2}'|data:|blob:)$")
# 'unsafe-inline' only where the policy above uses it.
UNSAFE_INLINE_OK = {"style-src"}

RESOURCE_ATTRS = {
    "script": ("src",),
    "link": ("href",),
    "img": ("src", "srcset"),
    "source": ("src", "srcset"),
    "iframe": ("src",),
    "frame": ("src",),
    "embed": ("src",),
    "object": ("data",),
    "video": ("src", "poster"),
    "audio": ("src",),
    "track": ("src",),
    "input": ("src",),
    "image": ("href", "xlink:href"),
    "use": ("href", "xlink:href"),
}
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)
CSS_URL = re.compile(r"""url\(\s*(['"]?)([^'")]*)\1\s*\)""", re.I)
CSS_IMPORT = re.compile(r"""@import\s+(?:url\(\s*)?(['"]?)([^'")\s;]+)""", re.I)


def is_external(value):
    """Another host: a scheme other than data:/blob:, or a protocol-relative //."""
    v = value.strip()
    if v.startswith("//"):
        return True
    m = SCHEME.match(v)
    return bool(m) and m.group(0).lower() not in ("data:", "blob:")


def srcset_urls(value):
    return [part.strip().split()[0] for part in value.split(",") if part.strip()]


def sha256_source(text):
    return "'sha256-%s'" % base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii")


class Page(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs = []  # (tag, attr, value, line)
        self.css = []  # (where, text, line)
        self.csp = []  # (content, line, scripts_seen_before)
        self.inline_scripts = []
        self.scripts = 0
        self._in = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0]
        a = {k.lower(): (v or "") for k, v in attrs}
        for attr in RESOURCE_ATTRS.get(tag, ()):
            if attr in a:
                values = srcset_urls(a[attr]) if attr == "srcset" else [a[attr]]
                self.refs.extend((tag, attr, v, line) for v in values)
        if "style" in a:
            self.css.append(("style attribute of <%s>" % tag, a["style"], line))
        if tag == "meta" and a.get("http-equiv", "").lower() == "content-security-policy":
            self.csp.append((a.get("content", ""), line, self.scripts))
        if tag == "script":
            self.scripts += 1
            if "src" not in a:
                self._in, self._buf = ("script", line), []
        elif tag == "style":
            self._in, self._buf = ("style", line), []

    def handle_data(self, data):
        if self._in is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if self._in is not None and tag == self._in[0]:
            text = "".join(self._buf)
            if tag == "script":
                self.inline_scripts.append(text)
            else:
                self.css.append(("<style>", text, self._in[1]))
            self._in = None


def raw_inline_scripts(text):
    # The hash covers the element's text exactly as written; html.parser would
    # decode nothing inside <script> either, but read it raw to be sure.
    return re.findall(r"<script\b(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script\s*>", text, re.S | re.I)


def parse_policy(content):
    policy = {}
    for part in content.split(";"):
        tokens = part.split()
        if tokens:
            policy[tokens[0].lower()] = tokens[1:]
    return policy


def cmd_localize(args):
    with open(args.page, encoding="utf-8") as fh:
        text = fh.read()
    srcs = re.findall(r"<script\b[^>]*\bsrc=\"([^\"]+)\"", text, re.I)
    if srcs != [args.bundle_url]:
        print("FAIL the page loads %r; expected exactly [%s]" % (srcs, args.bundle_url))
        return 1
    with open(args.bundle_file, "rb") as fh:
        bundle = fh.read()
    quoted = ('"%s"' % args.asset_url).encode("utf-8")
    if bundle.count(quoted) != 1:
        print("FAIL %s names %s %d time(s); expected exactly 1" % (args.bundle_file, args.asset_url, bundle.count(quoted)))
        return 1
    bundle = bundle.replace(quoted, ('"%s"' % args.asset_local).encode("utf-8"))
    with open(args.bundle_file, "wb") as fh:
        fh.write(bundle)
    integrity = "sha384-" + base64.b64encode(hashlib.sha384(bundle).digest()).decode("ascii")
    tag = re.search(r"<script\b[^>]*\bsrc=\"%s\"[^>]*>" % re.escape(args.bundle_url), text, re.I)
    new_tag = tag.group(0).replace('src="%s"' % args.bundle_url, 'src="%s"' % os.path.basename(args.bundle_file))
    new_tag, n = re.subn(r'integrity="[^"]*"', 'integrity="%s"' % integrity, new_tag)
    if n != 1:
        print("FAIL the bundle's <script> carries no integrity attribute to rewrite")
        return 1
    text = text[: tag.start()] + new_tag + text[tag.end():]
    if re.search(r"http-equiv=\"content-security-policy\"", text, re.I):
        print("FAIL the page already carries a Content-Security-Policy")
        return 1
    hashes = " ".join(sha256_source(s) for s in raw_inline_scripts(text))
    meta = '<meta http-equiv="Content-Security-Policy" content="%s">' % POLICY.format(hashes=hashes)
    charset = re.search(r"<meta\s+charset=[^>]*>", text, re.I)
    if charset is None:
        print("FAIL no <meta charset> to place the policy after")
        return 1
    text = text[: charset.end()] + meta + text[charset.end():]
    with open(args.page, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("site-page: localized %s -> %s (%s), %s -> %s; policy with %d inline script hash(es)"
          % (args.bundle_url, os.path.basename(args.bundle_file), integrity, args.asset_url,
             args.asset_local, len(raw_inline_scripts(text))))
    return 0


def cmd_check(args):
    index = os.path.join(args.site, "index.html")
    try:
        with open(index, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print("CANNOT CHECK: %s" % exc)
        return 1
    page = Page()
    page.feed(text)
    page.close()
    errors = []

    for tag, attr, value, line in page.refs:
        if is_external(value):
            errors.append("index.html:%d: <%s %s> loads from another host: %s" % (line, tag, attr, value))
        elif tag in ("script", "link") and value and not SCHEME.match(value):
            local = os.path.normpath(os.path.join(args.site, value.split("#")[0].split("?")[0]))
            if not os.path.isfile(local):
                errors.append("index.html:%d: <%s %s=%s> is not in the site" % (line, tag, attr, value))
    for where, css, line in page.css:
        for m in list(CSS_URL.finditer(css)) + list(CSS_IMPORT.finditer(css)):
            if is_external(m.group(2)):
                errors.append("index.html:%d: %s loads from another host: %s" % (line, where, m.group(2)))

    if page.scripts == 0:
        errors.append("index.html has no script at all: this is not the built page")
    if len(page.csp) != 1:
        errors.append("index.html carries %d Content-Security-Policy <meta>; expected exactly 1" % len(page.csp))
    else:
        content, line, before = page.csp[0]
        if before:
            errors.append("index.html:%d: the policy comes after %d script(s), which it does not cover" % (line, before))
        policy = parse_policy(content)
        if policy.get("default-src") != ["'none'"]:
            errors.append("index.html:%d: default-src is %r, not 'none'" % (line, policy.get("default-src")))
        for directive, sources in policy.items():
            for source in sources:
                if not ALLOWED_SOURCES.match(source):
                    errors.append("index.html:%d: %s allows %s" % (line, directive, source))
                elif source == "'unsafe-inline'" and directive not in UNSAFE_INLINE_OK:
                    errors.append("index.html:%d: %s allows 'unsafe-inline'" % (line, directive))
        listed = set(policy.get("script-src", []))
        for i, script in enumerate(raw_inline_scripts(text), 1):
            if sha256_source(script) not in listed:
                errors.append("index.html: inline script %d is not in script-src; the browser would block it" % i)

    for error in errors:
        print("FAIL %s" % error)
    if errors:
        print("site-page: %d problem(s) in %s" % (len(errors), index))
        return 1
    print("site-page: ok - %d resource reference(s), all from this site; %d inline script(s) hashed; "
          "one policy, before every script, naming no host" % (len(page.refs), len(page.inline_scripts)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    loc = sub.add_parser("localize")
    loc.add_argument("--page", required=True)
    loc.add_argument("--bundle-url", required=True)
    loc.add_argument("--bundle-file", required=True)
    loc.add_argument("--asset-url", required=True)
    loc.add_argument("--asset-local", required=True)
    chk = sub.add_parser("check")
    chk.add_argument("site")
    args = parser.parse_args(argv)
    return cmd_localize(args) if args.cmd == "localize" else cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
