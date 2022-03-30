import hashlib

from jobgraph.parameters import get_repo
from jobgraph.util import path as mozpath
from jobgraph.util.memoize import memoize


@memoize
def hash_path(path):
    """Hash a single file.

    Returns the SHA-256 hash in hex form.
    """
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def hash_paths(root_dir, patterns):
    """
    Give a list of path patterns, return a digest of the contents of all
    the corresponding files, similarly to git tree objects.
    Patterns must be relative to the root of the git repository. Only
    tracked files are hashed.

    Each file is hashed. The list of all hashes and file paths is then
    itself hashed to produce the result.
    """
    h = hashlib.sha256()

    found = set()
    for pattern in patterns:
        matched_tracked_files = _get_tracked_files_for_pattern(root_dir, pattern)
        if matched_tracked_files:
            found.update(matched_tracked_files)
        else:
            raise Exception(f"{pattern} did not match anything")
    for path in sorted(found):
        hash = hash_path(mozpath.normsep(path))
        h.update(f"{hash} {path}\n".encode())
    return h.hexdigest()


@memoize
def _get_tracked_files_for_pattern(root_dir, pattern):
    tracked_files = get_repo(root_dir).tracked_files
    return {path for path in tracked_files if mozpath.match(str(path), pattern)}
