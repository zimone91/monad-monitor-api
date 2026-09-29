"""Shared helpers for the repository checks. Python 3 standard library only.

The checks read the spec as JSON. CI converts openapi/openapi.yaml with the
pinned Redocly CLI (`redocly bundle --ext json`, see setup-npm-tools.sh), so no
YAML parser is needed here.

Run as a script, it prints the prose of the spec (titles, summaries and
descriptions, never example values) as Markdown, so that Vale and typos can
check the spec text with the same rules as the documents:

    python3 oas.py prose build/openapi.json > build/spec-prose.md
"""

import json
import re
import sys

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
API_BASE = "https://api.zim.one/v1"

# Keywords that change which keys an object may carry in ways the
# undocumented-field walker does not model. Meeting one is a hard stop
# ("cannot check"), never a silent pass.
UNSUPPORTED_KEYWORDS = ("if", "then", "else", "dependentSchemas", "dependencies")


class CannotCheck(Exception):
    """The input cannot be checked; the caller must fail closed."""


def load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise CannotCheck("cannot read JSON from %s: %s" % (path, exc))


def resolve_pointer(doc, ref):
    if not ref.startswith("#"):
        raise CannotCheck("external $ref is not supported: %s" % ref)
    node = doc
    for raw in ref[1:].split("/")[1:]:
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                raise CannotCheck("dangling $ref: %s" % ref)
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise CannotCheck("dangling $ref: %s" % ref)
    return node


def deref(doc, node, depth=0):
    """Follow $ref chains. A $ref with sibling keywords (allowed in OpenAPI
    3.1) is returned as allOf[target, siblings]."""
    if depth > 64:
        raise CannotCheck("$ref chain too deep (cycle?)")
    if isinstance(node, dict) and "$ref" in node:
        target = resolve_pointer(doc, node["$ref"])
        siblings = {k: v for k, v in node.items() if k != "$ref"}
        target = deref(doc, target, depth + 1)
        if siblings:
            return {"allOf": [target, siblings]}
        return target
    return node


def operations(doc):
    """Yield (method, path, operation) for every operation under `paths`."""
    for path, item in sorted((doc.get("paths") or {}).items()):
        item = deref(doc, item)
        for method in HTTP_METHODS:
            if isinstance(item, dict) and isinstance(item.get(method), dict):
                yield method, path, item[method]


def response(doc, op, code="200"):
    responses = op.get("responses") or {}
    if code not in responses:
        return None
    return deref(doc, responses[code])


def json_media(doc, op, code="200"):
    """The application/json media type object of a response, or None."""
    resp = response(doc, op, code)
    if not isinstance(resp, dict):
        return None
    content = resp.get("content") or {}
    for mtype, media in content.items():
        if mtype.split(";")[0].strip().lower() == "application/json":
            return media
    return None


def path_regex(template):
    """/validator/{id}/score -> ^/validator/[^/]+/score$"""
    parts = re.split(r"(\{[^}/]+\})", template)
    out = []
    for part in parts:
        if part.startswith("{") and part.endswith("}"):
            out.append(r"[^/?#]+")
        else:
            out.append(re.escape(part))
    return re.compile("^" + "".join(out) + "$")


def json_equal(a, b):
    """JSON equality: booleans never equal numbers; 1 and 1.0 are equal."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(json_equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


# --------------------------------------------------------------------------
# Undocumented fields
#
# A key in a JSON body is documented when the response schema declares it:
# listed under `properties`, matched by a `patternProperties` pattern, or
# accepted by an explicit `additionalProperties` / `unevaluatedProperties`
# (a schema, or `true`: the author declared an open map). Composition is
# followed: allOf merges what each branch declares; oneOf/anyOf need one
# branch under which the whole value is documented. A schema that declares
# nothing about keys documents none, so `{type: object}` alone with keys in
# the body is reported. Types and formats are not judged here; that is the
# schema validator's job (Spectral).
# --------------------------------------------------------------------------


class _Shape(object):
    __slots__ = ("props", "patterns", "extra", "items", "prefix")

    def __init__(self):
        self.props = {}       # key -> [schema, ...]
        self.patterns = []    # [(compiled regex, schema), ...]
        self.extra = []       # [schema, ...]; True means any key is declared
        self.items = []       # [schema, ...] for array elements
        self.prefix = []      # [[schema, ...], ...] per position (prefixItems)

    def merged(self, other):
        new = _Shape()
        new.props = {k: list(v) for k, v in self.props.items()}
        for k, v in other.props.items():
            new.props.setdefault(k, []).extend(v)
        new.patterns = self.patterns + other.patterns
        new.extra = self.extra + other.extra
        new.items = self.items + other.items
        width = max(len(self.prefix), len(other.prefix))
        new.prefix = []
        for i in range(width):
            left = self.prefix[i] if i < len(self.prefix) else []
            right = other.prefix[i] if i < len(other.prefix) else []
            new.prefix.append(left + right)
        return new


def _shapes(doc, schema, depth=0):
    if depth > 48:
        raise CannotCheck("schema nesting too deep (cycle through allOf/oneOf?)")
    schema = deref(doc, schema)
    base = _Shape()
    if schema is True or schema is False or not isinstance(schema, dict):
        return [base]
    for keyword in UNSUPPORTED_KEYWORDS:
        if keyword in schema:
            raise CannotCheck("schema keyword %r is not supported by the undocumented-field check" % keyword)
    for key, sub in (schema.get("properties") or {}).items():
        base.props.setdefault(key, []).append(sub)
    for pattern, sub in (schema.get("patternProperties") or {}).items():
        base.patterns.append((re.compile(pattern), sub))
    for keyword in ("additionalProperties", "unevaluatedProperties"):
        if keyword in schema and schema[keyword] is not False:
            base.extra.append(schema[keyword])
    if "items" in schema and schema["items"] is not False:
        base.items.append(schema["items"])
    for sub in schema.get("prefixItems") or []:
        base.prefix.append([sub])
    shapes = [base]
    for sub in schema.get("allOf") or []:
        shapes = [a.merged(b) for a in shapes for b in _shapes(doc, sub, depth + 1)]
    for keyword in ("oneOf", "anyOf"):
        if keyword in schema:
            branches = []
            for sub in schema[keyword]:
                branches.extend(_shapes(doc, sub, depth + 1))
            shapes = [a.merged(b) for a in shapes for b in branches]
    return shapes


def _first_clean(results):
    """Given problem lists from alternatives, return [] if any is clean, else
    the shortest list (the closest alternative explains the failure best)."""
    best = None
    for problems in results:
        if not problems:
            return []
        if best is None or len(problems) < len(best):
            best = problems
    return best or []


def undocumented(doc, value, schema, path="$"):
    """Return a list of 'path: message' strings for undocumented keys."""
    return _first_clean(_check_shape(doc, value, shape, path) for shape in _shapes(doc, schema))


def _check_shape(doc, value, shape, path):
    problems = []
    if isinstance(value, dict):
        for key in value:
            child = "%s.%s" % (path, key)
            candidates = list(shape.props.get(key, []))
            candidates += [sub for rx, sub in shape.patterns if rx.search(key)]
            if not candidates:
                if any(extra is True for extra in shape.extra):
                    continue
                candidates = [extra for extra in shape.extra if extra is not True]
            if not candidates:
                problems.append("%s: key is not declared in the response schema" % child)
                continue
            problems.extend(_first_clean(undocumented(doc, value[key], sub, child) for sub in candidates))
    elif isinstance(value, list):
        for index, element in enumerate(value):
            child = "%s[%d]" % (path, index)
            candidates = list(shape.prefix[index]) if index < len(shape.prefix) else []
            if not candidates:
                candidates = list(shape.items)
            if not candidates:
                candidates = [{}]  # nothing declared: keys inside will be reported
            problems.extend(_first_clean(undocumented(doc, element, sub, child) for sub in candidates))
    return problems


def dedupe_paths(problems):
    """Collapse array indexes so one missing key in 200 elements is one line."""
    seen, out = set(), []
    for problem in problems:
        generic = re.sub(r"\[\d+\]", "[*]", problem)
        if generic not in seen:
            seen.add(generic)
            out.append(generic)
    return out


# --------------------------------------------------------------------------
# Prose extraction (for Vale and typos)
# --------------------------------------------------------------------------

PROSE_KEYS = ("title", "summary", "description")
SKIP_KEYS = ("example", "examples", "default", "enum", "const")


def prose(doc):
    """Yield (location, text) for every human-written string in the spec.
    Example values, defaults, enums and constants are data, not prose, and
    are skipped; the `summary`/`description` of an Example Object are ours
    and are kept."""
    stack = [("$", doc, False)]
    while stack:
        loc, node, in_examples = stack.pop()
        if isinstance(node, dict):
            for key in sorted(node, reverse=True):
                val = node[key]
                here = "%s.%s" % (loc, key)
                if in_examples:
                    # inside `examples`: map of name -> Example Object
                    if isinstance(val, dict):
                        for ekey in ("summary", "description"):
                            if isinstance(val.get(ekey), str):
                                stack.append(("%s.%s" % (here, ekey), val[ekey], False))
                    continue
                if key in PROSE_KEYS and isinstance(val, str):
                    stack.append((here, val, False))
                elif key == "examples" and isinstance(val, dict):
                    stack.append((here, val, True))
                elif key in SKIP_KEYS:
                    continue
                else:
                    stack.append((here, val, False))
        elif isinstance(node, list):
            for index in range(len(node) - 1, -1, -1):
                stack.append(("%s[%d]" % (loc, index), node[index], False))
        elif isinstance(node, str) and loc.rsplit(".", 1)[-1] in PROSE_KEYS:
            yield loc, node


def main(argv):
    if len(argv) != 3 or argv[1] != "prose":
        sys.stderr.write("usage: oas.py prose SPEC.json\n")
        return 2
    try:
        doc = load_json(argv[2])
    except CannotCheck as exc:
        sys.stderr.write("CANNOT CHECK: %s\n" % exc)
        return 1
    count = 0
    out = sys.stdout
    out.write("# Prose extracted from the OpenAPI document\n\n")
    for loc, text in prose(doc):
        count += 1
        out.write("<!-- %s -->\n\n%s\n\n" % (loc.replace("--", "- -"), text.strip()))
    if count == 0:
        sys.stderr.write("CANNOT CHECK: no prose found in %s\n" % argv[2])
        return 1
    sys.stderr.write("ok - %d prose string(s) extracted\n" % count)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
