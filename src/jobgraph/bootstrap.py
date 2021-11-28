import os
import shutil
from pathlib import Path

from jobgraph.config import GraphConfig, load_graph_config
from jobgraph.paths import (
    BOOTSTRAP_DIR,
    get_gitlab_ci_dir,
    get_gitlab_ci_yml_path,
    get_terraform_dir,
)
from jobgraph.util.terraform import terraform_apply, terraform_init
from jobgraph.util.vcs import get_repository


def bootstrap(
    gitlab_project_id, gitlab_root_url, jobgraph_bot_username, jobgraph_bot_gitlab_token
):
    cwd = Path.cwd()
    get_repository(cwd)
    copy_bootstrap_folder(cwd)
    generate_gitlab_ci_yml(cwd)
    generate_config_yml(cwd, gitlab_project_id, gitlab_root_url)
    setup_repo_secrets(
        gitlab_project_id,
        gitlab_root_url,
        jobgraph_bot_username,
        jobgraph_bot_gitlab_token,
    )


def copy_bootstrap_folder(cwd):
    for path in BOOTSTRAP_DIR.glob("**/*"):
        if not path.is_file():
            continue

        relative_path = path.relative_to(BOOTSTRAP_DIR)
        target_path = cwd / relative_path
        target_dir = target_path.parent
        os.makedirs(target_dir, exist_ok=True)
        shutil.copy(path, target_path)


def generate_gitlab_ci_yml(cwd):
    source_gitlab_ci_yml = get_gitlab_ci_yml_path()

    with open(source_gitlab_ci_yml) as f:
        gitlab_ci_yml_lines = f.readlines()

    target_lines = [
        line
        for line in gitlab_ci_yml_lines
        if all(
            excluded_line not in line
            for excluded_line in (
                # These lines are specific to the jobgraph repo itself
                "# We reinstall jobgraph",
                "- pip install --prefix ",
            )
        )
    ]

    with open(get_gitlab_ci_yml_path(root_dir=cwd), "w") as f:
        f.writelines(target_lines)


def generate_config_yml(cwd, gitlab_project_id, gitlab_root_url):
    graph_config = load_graph_config()
    graph_config["gitlab"]["project_id"] = gitlab_project_id
    graph_config["gitlab"]["root_url"] = gitlab_root_url

    target_graph_config = GraphConfig(
        config=dict(graph_config._config), root_dir=str(get_gitlab_ci_dir(cwd))
    )
    target_graph_config.write()


def setup_repo_secrets(
    gitlab_project_id, gitlab_root_url, jobgraph_bot_username, jobgraph_bot_gitlab_token
):
    terraform_dir = get_terraform_dir(root_dir=BOOTSTRAP_DIR)

    terraform_init(
        terraform_dir=terraform_dir,
        gitlab_project_id=gitlab_project_id,
        gitlab_root_url=gitlab_root_url,
        terraform_username=jobgraph_bot_username,
        terraform_password=jobgraph_bot_gitlab_token,
        upgrade_providers=False,
    )

    apply_variables = {
        "GITLAB_PROJECT_ID": gitlab_project_id,
        "JOBGRAPH_BOT_GITLAB_TOKEN": jobgraph_bot_gitlab_token,
    }
    terraform_apply(terraform_dir, **apply_variables)