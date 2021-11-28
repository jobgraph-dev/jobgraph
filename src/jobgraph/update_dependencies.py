import hashlib
import logging
import os
from pathlib import Path
from subprocess import CalledProcessError

import requests
from dockerfile_parse import DockerfileParser

from jobgraph.config import load_graph_config
from jobgraph.paths import (
    JOBGRAPH_ROOT_DIR,
    PYTHON_VERSION_FILE,
    TFENV_FILE,
    get_gitlab_ci_dir,
    get_gitlab_ci_yml_path,
    get_terraform_dir,
    get_terraform_version_file,
)
from jobgraph.util.docker_registries import fetch_image_digest_from_registry, set_digest
from jobgraph.util.gitlab import convert_https_url_into_ssh
from jobgraph.util.subprocess import run_subprocess
from jobgraph.util.terraform import terraform_init
from jobgraph.util.vcs import get_repository

logger = logging.getLogger(__name__)


def update_dependencies(
    create_new_merge_request,
    git_committer_name,
    git_committer_email,
    git_remote_name,
    git_branch,
):
    repo_root = Path.cwd()

    if create_new_merge_request:
        _test_git_connection(repo_root, git_remote_name)

    graph_config = load_graph_config(
        root_dir=get_gitlab_ci_dir(repo_root), validate_config=False
    )

    is_upstream_jobgraph_being_updated = JOBGRAPH_ROOT_DIR == repo_root
    if is_upstream_jobgraph_being_updated:
        _update_jobgraph_python_requirements()
        _update_precommit_hooks()
        _update_tfenv()
        _update_terraform()
        _update_terraform_providers(graph_config)

    _update_dockerfiles(root_dir=repo_root)
    _update_decision_image()
    _update_external_images(graph_config)

    if create_new_merge_request:
        _create_merge_request(
            repo_root,
            git_committer_name,
            git_committer_email,
            git_remote_name,
            git_branch,
        )


def _test_git_connection(repo_root, git_remote_name):
    repo_url = get_repository(repo_root).get_url(remote=git_remote_name)
    ssh_url = convert_https_url_into_ssh(repo_url)
    ssh_test_url = ssh_url.split(":")[0]
    run_subprocess(["ssh", "-T", ssh_test_url])
    logger.info("Connection to remote repo is working.")


_PIN_COMMANDS = " && ".join(
    (
        "pip install --upgrade pip",
        "pip install pip-compile-multi",
        "pip-compile-multi --generate-hashes base --generate-hashes test --generate-hashes dev",
        "chmod 644 requirements/*.txt",
        f"chown {os.getuid()}:{os.getgid()} requirements/*.txt",
    )
)


def _update_jobgraph_python_requirements():
    with open(PYTHON_VERSION_FILE) as f:
        python_version = f.read().strip()

    docker_command = (
        "docker",
        "run",
        "--tty",
        "--volume",
        f"{JOBGRAPH_ROOT_DIR}:/src",
        "--workdir",
        "/src",
        "--pull",
        "always",
        f"python:{python_version}-alpine",
        "ash",
        "-c",
        _PIN_COMMANDS,
    )
    run_subprocess(docker_command)


def _update_precommit_hooks():
    precommit_command = (
        "pre-commit",
        "autoupdate",
    )
    run_subprocess(precommit_command)


def _update_dockerfiles(root_dir):
    for docker_file_path in root_dir.glob("**/Dockerfile"):
        docker_file = DockerfileParser(
            path=str(docker_file_path),
            env_replace=True,
        )
        base_image = docker_file.baseimage

        # base_image may not be defined if it's generated within jobgraph
        if base_image:
            new_digest = fetch_image_digest_from_registry(base_image)
            new_base_image = set_digest(base_image, new_digest)
            if new_base_image != base_image:
                logger.info(
                    f"Bumping base image in {docker_file_path} to: {new_base_image}"
                )
                docker_file.baseimage = new_base_image


_IMAGE_INSTRUCTION_PREFIX = "    image: "


# This implementation is quite basic and looks fragile at a first glance.
# Although, parsing .gitlab-ci.yml with pyyaml actually badly messes up the
# formatting.
# Moreover, the indentation is safeguarded by yamllint.
def _update_decision_image():
    with open(get_gitlab_ci_yml_path()) as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.startswith(_IMAGE_INSTRUCTION_PREFIX):
            image_full_location = line[len(_IMAGE_INSTRUCTION_PREFIX) :]
            image_new_full_location = set_digest(
                image_full_location,
                fetch_image_digest_from_registry(image_full_location),
            )

            line = f"{_IMAGE_INSTRUCTION_PREFIX}{image_new_full_location}\n"

        new_lines.append(line)

    with open(get_gitlab_ci_yml_path(), "w") as f:
        lines = f.writelines(new_lines)


def _update_external_images(graph_config):
    graph_config["docker"]["external_images"] = {
        image_name: set_digest(
            image_full_location,
            fetch_image_digest_from_registry(image_full_location),
        )
        for image_name, image_full_location in graph_config["docker"][
            "external_images"
        ].items()
    }
    graph_config.write()


def _update_tfenv():
    tag = _get_latest_tag_on_github_release("tfutils", "tfenv")
    sha256sum = _get_source_sha256_from_github("tfutils", "tfenv", tag)
    version = tag.lstrip("v")
    target_file_name = f"tfenv-{version}.tar.gz"
    with open(TFENV_FILE, "w") as f:
        f.write(f"{sha256sum}  {target_file_name}\n")


def _update_terraform():
    tag = _get_latest_tag_on_github_release("hashicorp", "terraform")
    version = tag.lstrip("v")
    with open(get_terraform_version_file(), "w") as f:
        f.write(f"{version}\n")


def _update_terraform_providers(graph_config):
    # Logic from https://gitlab.com/gitlab-org/terraform-images/-/blob/37f671b7abb6d29ee033fd7586b29caf7b270182/src/bin/gitlab-terraform.sh#L26 # noqa: E501
    terraform_username = os.environ.get(
        "TF_USERNAME", os.environ.get("GITLAB_USER_LOGIN")
    )
    terraform_password = os.environ.get(
        "TF_PASSWORD", os.environ.get("GITLAB_PERSONAL_TOKEN")
    )
    if not terraform_password:
        terraform_username = "gitlab-ci-token"
        terraform_password = os.environ["CI_JOB_TOKEN"]

    terraform_init(
        terraform_dir=get_terraform_dir(),
        gitlab_project_id=graph_config["gitlab"]["project_id"],
        gitlab_root_url=graph_config["gitlab"]["root_url"],
        terraform_username=terraform_username,
        terraform_password=terraform_password,
        terraform_state_name="jobgraph",
        upgrade_providers=True,
    )


def _get_latest_tag_on_github_release(repo_owner, repo_name):
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"
    response = requests.get(url)
    return response.json()["tag_name"]


def _get_source_sha256_from_github(repo_owner, repo_name, tag):
    url = f"https://codeload.github.com/{repo_owner}/{repo_name}/tar.gz/refs/tags/{tag}"
    response = requests.get(url)
    return hashlib.sha256(response.content).hexdigest()


def _create_merge_request(
    repo_root, git_committer_name, git_committer_email, git_remote_name, git_branch
):
    repo = get_repository(repo_root)

    current_branch = repo.branch
    repo.switch_branch(git_branch, force_create=True)

    try:
        repo.commit(
            git_committer_name,
            git_committer_email,
            message="Update jobgraph dependencies",
            commit_all_files=True,
        )
    except CalledProcessError:
        repo.switch_branch(current_branch)
        logger.info("No updates found. Nothing to commit")
        return

    repo_url = repo.get_url(remote=git_remote_name)
    ssh_url = convert_https_url_into_ssh(repo_url)
    repo.set_push_url(ssh_url)

    main_branch = repo.get_main_branch(git_remote_name, short_format=True)
    repo.push(
        git_remote_name,
        git_branch,
        force_push=True,
        push_options=[
            "merge_request.create",
            (
                "merge_request.description=This merge request was automatically created by"
                "jobgraph in `$CI_JOB_NAME` ([#$CI_JOB_ID]($CI_JOB_URL))."
            ),
            "merge_request.label=scheduled",
            "merge_request.label=update-dependencies",
            "merge_request.remove_source_branch",
            f"merge_request.target={main_branch}",
            "merge_request.title=Update jobgraph dependencies",
        ],
    )

    repo.switch_branch(current_branch)
