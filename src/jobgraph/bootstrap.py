import os
import shutil
from pathlib import Path

from jobgraph.config import GraphConfig, load_graph_config
from jobgraph.docker import get_image_full_location_with_digest
from jobgraph.paths import (
    BOOTSTRAP_DIR,
    GITLAB_CI_DIR,
    get_gitlab_ci_dir,
    get_gitlab_ci_yml_path,
    get_stages_dir,
    get_terraform_dir,
)
from jobgraph.util.terraform import terraform_apply, terraform_init
from jobgraph.util.vcs import get_repository


def bootstrap(
    gitlab_project_id, gitlab_root_url, jobgraph_bot_username, jobgraph_bot_gitlab_token
):
    cwd = Path.cwd()
    get_repository(cwd)
    copy_gitlab_ci_in_bootstrap_folder(cwd)
    generate_gitlab_ci_yml(cwd)
    generate_config_yml(cwd, gitlab_project_id, gitlab_root_url)
    setup_repo_secrets(
        gitlab_project_id,
        gitlab_root_url,
        jobgraph_bot_username,
        jobgraph_bot_gitlab_token,
    )
    generate_schedules_stage(cwd)
    generate_updates_stage(cwd)


def copy_gitlab_ci_in_bootstrap_folder(cwd):
    gitlab_ci_dir = get_gitlab_ci_dir(root_dir=BOOTSTRAP_DIR)
    for path in gitlab_ci_dir.glob("**/*"):
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
    graph_config["docker"]["external_images"][
        "jobgraph"
    ] = get_image_full_location_with_digest("decision", root_dir=GITLAB_CI_DIR)

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
        terraform_state_name="jobgraph-bootstrap",
        upgrade_providers=False,
    )

    apply_variables = {
        "GITLAB_PROJECT_ID": gitlab_project_id,
        "JOBGRAPH_BOT_GITLAB_TOKEN": jobgraph_bot_gitlab_token,
    }
    terraform_apply(terraform_dir, **apply_variables)


def generate_schedules_stage(cwd):
    return _copy_and_modify_stage(
        cwd,
        source_stage_yml_relative_path=Path("jobgraph_schedules/stage.yml"),
        forewords_lines=[
            "# This file lets jobgraph modify Gitlab CI schedules based on the\n",
            "# content of `gitlab-ci/schedules.yml`. Modify this current file\n",
            "# at your own risks.\n",
        ],
        lines_to_replace={
            "    image: {in_tree: decision}\n": '    image: {docker_image_reference: "<jobgraph>"}\n',  # noqa: E501
            "        TF_ROOT: ${CI_PROJECT_DIR}/terraform\n": "        TF_ROOT: /jobgraph/terraform\n",  # noqa: E501
        },
    )


def generate_updates_stage(cwd):
    return _copy_and_modify_stage(
        cwd,
        source_stage_yml_relative_path=Path("jobgraph_updates/stage.yml"),
        forewords_lines=[
            "# This file lets jobgraph update itself and any docker images it uses.\n",
            "# Modify this current file at your own risks.\n",
        ],
        lines_to_replace={
            "        image: {in_tree: decision}\n": '        image: {docker_image_reference: "<jobgraph>"}\n',  # noqa: E501
            "            --git-committer-email='10283475-jobgraph-bot@users.noreply.gitlab.com'\n": "            --git-committer-email='CHANGE-THIS@EMAIL.ADDRESS'\n",  # noqa: E501
        },
    )


def _copy_and_modify_stage(
    cwd,
    source_stage_yml_relative_path,
    forewords_lines,
    lines_to_replace,
):
    source_stage_yml_path = get_stages_dir() / source_stage_yml_relative_path

    with open(source_stage_yml_path) as f:
        schedules_yml_lines = f.readlines()

    target_stage_yml_lines = forewords_lines

    for line in schedules_yml_lines:
        if line in lines_to_replace:
            new_line = lines_to_replace[line]
            target_stage_yml_lines.append(new_line)
            continue

        target_stage_yml_lines.append(line)

    target_stage_dir = get_stages_dir(gitlab_ci_dir=get_gitlab_ci_dir(root_dir=cwd))
    target_stage_yml_path = target_stage_dir / source_stage_yml_relative_path

    target_dir = target_stage_yml_path.parent
    os.makedirs(target_dir, exist_ok=True)

    with open(target_stage_yml_path, "w") as f:
        f.writelines(target_stage_yml_lines)
