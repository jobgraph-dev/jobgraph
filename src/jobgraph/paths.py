from pathlib import Path

_SRC_DIR = Path(__file__).parent.parent.resolve()
JOBGRAPH_ROOT_DIR = _SRC_DIR.parent
GITLAB_CI_DIR = JOBGRAPH_ROOT_DIR / "gitlab-ci"

PYTHON_VERSION_FILE = JOBGRAPH_ROOT_DIR / "python-version.txt"
TFENV_FILE = GITLAB_CI_DIR / "docker" / "jobgraph_update" / "tfenv.sha256"
TERRAFORM_DIR = GITLAB_CI_DIR / "terraform"
TERRAFORM_VERSION_FILE = TERRAFORM_DIR / ".terraform-version"


def get_gitlab_ci_dir(root_dir=JOBGRAPH_ROOT_DIR):
    return Path(root_dir) / "gitlab-ci"


def get_stages_dir(gitlab_ci_dir=get_gitlab_ci_dir()):
    return Path(gitlab_ci_dir) / "stages"


def get_gitlab_ci_yml_path(root_dir=JOBGRAPH_ROOT_DIR):
    return Path(root_dir) / ".gitlab-ci.yml"


def get_config_yml_path(ci_dir=get_gitlab_ci_dir()):
    return Path.resolve(Path(ci_dir) / "config.yml")
