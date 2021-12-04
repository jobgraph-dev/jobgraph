import hashlib
from pathlib import Path

from jobgraph.util import path as mozpath
from jobgraph.util.memoize import memoize


@memoize
def hash_path(path):
    """Hash a single file.

    Returns the SHA-256 hash in hex form.
    """
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _find_files(base_path):
    for path in Path(base_path).rglob("*"):
        if path.is_file():
            yield str(path)


def hash_paths(base_path, patterns):
    """
    Give a list of path patterns, return a digest of the contents of all
    the corresponding files, similarly to git tree objects.

    Each file is hashed. The list of all hashes and file paths is then
    itself hashed to produce the result.
    """
    h = hashlib.sha256()

    found = set()
    for pattern in patterns:
        files = _find_files(base_path)
        matches = [path for path in files if mozpath.match(path, pattern)]
        if matches:
            found.update(matches)
        else:
            raise Exception(f"{pattern} did not match anything")
    for path in sorted(found):
        hash = hash_path(mozpath.abspath(mozpath.join(base_path, path)))
        path = mozpath.normsep(path)
        h.update(f"{hash} {path}\n".encode())
    return h.hexdigest()
