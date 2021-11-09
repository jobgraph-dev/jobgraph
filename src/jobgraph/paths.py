import pathlib

_SRC_DIR = pathlib.Path(__file__).parent.parent.resolve()
ROOT_DIR = _SRC_DIR.parent

PYTHON_VERSION_FILE = ROOT_DIR / "python-version.txt"
