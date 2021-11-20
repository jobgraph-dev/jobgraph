import logging
import hashlib
import os
import subprocess

import requests
from dockerfile_parse import DockerfileParser

from jobgraph.paths import PYTHON_VERSION_FILE, ROOT_DIR, TERRAFORM_DIR, TFENV_FILE, TERRAFORM_VERSION_FILE
from jobgraph.util.docker_registries import fetch_image_digest_from_registry, set_digest

logger = logging.getLogger(__name__)


def update_dependencies(graph_config):
    _update_jobgraph_python_requirements()
    _update_dockerfiles()
    _update_docker_in_docker_image(graph_config)
    _update_tfenv()
    _update_terraform()
    _update_terraform_providers()


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
        f"{ROOT_DIR}:/src",
        "--workdir",
        "/src",
        "--pull",
        "always",
        f"python:{python_version}-alpine",
        "ash",
        "-c",
        _PIN_COMMANDS,
    )
    subprocess.run(docker_command)


def _update_dockerfiles():
    for docker_file_path in ROOT_DIR.glob("**/Dockerfile"):
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


def _update_docker_in_docker_image(graph_config):
    graph_config["docker"]["external-images"] = {
        image_name: set_digest(
            image_full_location,
            fetch_image_digest_from_registry(image_full_location),
        )
        for image_name, image_full_location in graph_config["docker"][
            "external-images"
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
    with open(TERRAFORM_VERSION_FILE, "w") as f:
        f.write(f"{version}\n")


def _update_terraform_providers():
    terraform_command = [
        "terraform",
        "init",
        "-upgrade",
    ]
    subprocess.run(terraform_command, cwd=TERRAFORM_DIR)


def _get_latest_tag_on_github_release(repo_owner, repo_name):
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"
    response = requests.get(url)
    return response.json()["tag_name"]


def _get_source_sha256_from_github(repo_owner, repo_name, tag):
    url = f"https://codeload.github.com/{repo_owner}/{repo_name}/tar.gz/refs/tags/{tag}"
    response = requests.get(url)
    return hashlib.sha256(response.content).hexdigest()
