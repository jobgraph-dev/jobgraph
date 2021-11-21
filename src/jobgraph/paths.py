import pathlib

_SRC_DIR = pathlib.Path(__file__).parent.parent.resolve()
ROOT_DIR = _SRC_DIR.parent
GITLAB_CI_DIR = ROOT_DIR / "gitlab-ci"

GITLAB_CI_YML_FILE = ROOT_DIR / ".gitlab-ci.yml"
PYTHON_VERSION_FILE = ROOT_DIR / "python-version.txt"
TFENV_FILE = GITLAB_CI_DIR / "docker" / "jobgraph_update" / "tfenv.sha256"
TERRAFORM_DIR = GITLAB_CI_DIR / "terraform"
TERRAFORM_VERSION_FILE = TERRAFORM_DIR / ".terraform-version"
