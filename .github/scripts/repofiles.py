"""List and read the files a content check must cover. Standard library only.

Default: every file git tracks (`git ls-files -z`), which is exactly what the
public repository publishes. `--walk DIR` walks a directory instead (for a
tree that is not a git checkout); it skips .git and node_modules only.

Reading fails closed: a file that is not UTF-8 text is an error, not a pass,
unless its extension marks it as a binary format the checks cannot contain
text in (images, fonts, archives). The caller prints how many files and
lines it checked, so "ok" can never mean "nothing was read".
"""

import os
import subprocess

BINARY_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".zip", ".gz", ".tgz", ".xz", ".bz2", ".7z", ".pdf",
)


class ReadError(Exception):
    pass


def list_files(walk_root=None):
    if walk_root:
        found = []
        for base, dirs, files in os.walk(walk_root):
            dirs[:] = sorted(d for d in dirs if d not in (".git", "node_modules"))
            for name in sorted(files):
                found.append(os.path.relpath(os.path.join(base, name), walk_root))
        return walk_root, found
    try:
        out = subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReadError("git ls-files failed (%s); run inside the checkout or pass --walk DIR" % exc)
    # ls-files prints paths relative to the current directory
    names = [n for n in out.decode("utf-8", "surrogateescape").split("\0") if n]
    return os.getcwd(), names


def read_text(root, name):
    """Return the file's text, None for a known binary format, or raise."""
    path = os.path.join(root, name)
    if name.lower().endswith(BINARY_EXTENSIONS):
        return None
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise ReadError("%s: cannot read (%s)" % (name, exc))
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReadError("%s: not UTF-8 text (%s); cannot check it" % (name, exc))
