import logging
import os
import shutil
from copy import copy
from pathlib import Path

from jobgraph.config import GraphConfig, load_graph_config
from jobgraph.paths import (
    BOOTSTRAP_DIR,
    JOBGRAPH_ROOT_DIR,
    get_gitlab_ci_dir,
    get_gitlab_ci_yml_path,
    get_stages_dir,
    get_terraform_dir,
)
from jobgraph.util.terraform import terraform_apply, terraform_init
from jobgraph.util.vcs import get_repository

logger = logging.getLogger(__name__)


def bootstrap(
    gitlab_project_id,
    gitlab_root_url,
    jobgraph_bot_username,
    jobgraph_bot_gitlab_token,
    maintainer_username,
    maintainer_gitlab_token,
):
    cwd = Path.cwd()
    get_repository(cwd)  # Ensure we're at the root of a git repo
    os.environ["CI_REGISTRY_USER"] = maintainer_username
    os.environ["CI_REGISTRY_PASSWORD"] = maintainer_gitlab_token
    copy_gitlab_ci_in_bootstrap_folder(cwd)
    generate_gitlab_ci_yml(cwd)
    generate_config_yml(cwd, gitlab_project_id, gitlab_root_url)
    generate_schedules_stage(cwd)
    generate_updates_stage(cwd)
    generate_tests_stage(cwd)
    setup_repo_secrets(
        gitlab_project_id,
        gitlab_root_url,
        jobgraph_bot_username,
        jobgraph_bot_gitlab_token,
        maintainer_username,
        maintainer_gitlab_token,
    )


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

    graph_config["jobgraph"][
        "decision_parameters"
    ] = "local_jobgraph.parameters:get_decision_parameters"
    graph_config["jobgraph"]["register"] = "local_jobgraph:register"

    target_graph_config = GraphConfig(
        config=dict(graph_config._config), root_dir=str(get_gitlab_ci_dir(cwd))
    )
    target_graph_config.write()


def setup_repo_secrets(
    gitlab_project_id,
    gitlab_root_url,
    jobgraph_bot_username,
    jobgraph_bot_gitlab_token,
    maintainer_username,
    maintainer_gitlab_token,
):
    terraform_dir = get_terraform_dir(root_dir=BOOTSTRAP_DIR)

    terraform_init(
        terraform_dir=terraform_dir,
        gitlab_project_id=gitlab_project_id,
        gitlab_root_url=gitlab_root_url,
        terraform_username=maintainer_username,
        terraform_password=maintainer_gitlab_token,
        terraform_state_name="jobgraph-bootstrap",
        upgrade_providers=False,
    )

    apply_variables = {
        "GITLAB_PROJECT_ID": gitlab_project_id,
        "JOBGRAPH_BOT_GITLAB_TOKEN": jobgraph_bot_gitlab_token,
        "MAINTAINER_GITLAB_TOKEN": maintainer_gitlab_token,
    }
    terraform_apply(terraform_dir, **apply_variables)
    logging.info(
        f"Please add the SSH public key above to {jobgraph_bot_username}'s "
        "keys (https://gitlab.com/-/profile/keys)"
    )


def generate_schedules_stage(cwd):
    _copy_and_modify_stage(
        cwd,
        source_stage_yml_relative_path=Path("jobgraph_schedules/stage.yml"),
        forewords_lines=[
            "# This file lets jobgraph modify Gitlab CI schedules based on the\n",
            "# content of `gitlab-ci/schedules.yml`. Modify this current file\n",
            "# at your own risks.\n",
        ],
        lines_to_replace={
            "    image: {in_tree: jobgraph}\n": '    image: {docker_image_reference: "<jobgraph>"}\n',  # noqa: E501
            "        TF_ROOT: ${CI_PROJECT_DIR}/terraform\n": "        TF_ROOT: /jobgraph/terraform\n",  # noqa: E501
        },
    )


def generate_updates_stage(cwd):
    _copy_and_modify_stage(
        cwd,
        source_stage_yml_relative_path=Path("jobgraph_updates/stage.yml"),
        forewords_lines=[
            "# This file lets jobgraph update itself and any docker images it uses.\n",
            "# Modify this current file at your own risks.\n",
        ],
        lines_to_replace={
            "        image: {in_tree: jobgraph}\n": '        image: {docker_image_reference: "<jobgraph>"}\n',  # noqa: E501
            '        - pip install --prefix "/runner/.local" --no-deps --editable "$CI_PROJECT_DIR"\n': "",  # noqa: E501
            "            --git-committer-email='10283475-jobgraph-bot@users.noreply.gitlab.com'\n": "            --git-committer-email='CHANGE-THIS@EMAIL.ADDRESS'\n",  # noqa: E501
        },
    )


_TEST_STAGE_FOREWORD = [
    "# This stage ensure your jobgraph definitions are correctly linted.\n",
    "# Modify this current file at your own risks.\n",
]


def generate_tests_stage(cwd):
    _copy_and_modify_stage(
        cwd,
        source_stage_yml_relative_path=Path("jobgraph_tests/stage.yml"),
        forewords_lines=_TEST_STAGE_FOREWORD,
        lines_to_replace={
            "- jobgraph.transforms.reinstall_jobgraph:transforms\n": "",
            "        JOBGRAPH_ROOT_DIR: $CI_PROJECT_DIR\n": "        JOBGRAPH_ROOT_DIR: $CI_PROJECT_DIR/gitlab-ci\n",  # noqa: E501
        },
    )

    _copy_and_modify_stage(
        cwd,
        source_stage_yml_relative_path=Path("jobgraph_tests/dockerfiles.yml"),
        forewords_lines=_TEST_STAGE_FOREWORD,
        lines_to_replace={
            '        - "**/Dockerfile"\n': '        - "gitlab-ci/**/Dockerfile"',
        },
    )

    _copy_and_modify_stage(
        cwd,
        source_stage_yml_relative_path=Path("jobgraph_tests/python.yml"),
        forewords_lines=_TEST_STAGE_FOREWORD,
        lines_to_replace={
            '        - "**/*.py"\n': '        - "gitlab-ci/**/*.py"',
            "    image: {in_tree: python_test}\n": '    image: {"docker_image_reference": "<jobgraph_tests>"}\n',  # noqa: E501
            # The following line is even a bigger hack than the simple search-and-
            # replace strategy currently implemented. It strips the \n so that
            # the generated file doesn't end with to \n\n which makes yamllint
            # unhappy.
            #
            # TODO: Implement a much nicer search-and-replace strategy.
            """    script: pyupgrade --py310-plus $(find "$JOBGRAPH_ROOT_DIR" -name '*.py')\n""": """    script: pyupgrade --py310-plus $(find "$JOBGRAPH_ROOT_DIR" -name '*.py')""",  # noqa: E501
            "unit:\n": "",
            '    description: "Run `unit tests` to validate the latest changes"\n': "",
            "    reinstall_jobgraph: true\n": "",
            "    script: pytest --pyargs jobgraph\n": "",
        },
    )

    _copy_and_modify_stage(
        cwd,
        source_stage_yml_relative_path=Path("jobgraph_tests/yaml.yml"),
        forewords_lines=_TEST_STAGE_FOREWORD,
        lines_to_replace={
            '        - "**/*.yml"\n': '        - "gitlab-ci/**/*.yml"',
            "    image: {in_tree: python_test}\n": '    image: {"docker_image_reference": "<jobgraph_tests>"}\n',  # noqa: E501
        },
    )

    for lint_config_file in (".flake8", ".yamllint", "pyproject.toml"):
        shutil.copy(
            JOBGRAPH_ROOT_DIR / lint_config_file,
            get_gitlab_ci_dir(root_dir=cwd) / lint_config_file,
        )


def _copy_and_modify_stage(
    cwd,
    source_stage_yml_relative_path,
    forewords_lines,
    lines_to_replace,
):
    source_stage_yml_path = get_stages_dir() / source_stage_yml_relative_path

    with open(source_stage_yml_path) as f:
        source_stage_lines = f.readlines()

    target_stage_yml_lines = copy(forewords_lines)

    for line in source_stage_lines:
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
