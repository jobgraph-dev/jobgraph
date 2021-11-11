import logging
import os
import subprocess

from dockerfile_parse import DockerfileParser

from jobgraph.paths import PYTHON_VERSION_FILE, ROOT_DIR
from jobgraph.util.docker_registries import fetch_image_digest_from_registry, set_digest

logger = logging.getLogger(__name__)


def update_dependencies(options):
    _update_jobgraph_python_requirements()
    _update_dockerfiles()


_PIN_COMMANDS = " && ".join(
    (
        "pip install --upgrade pip",
        "pip install pip-compile-multi",
        "pip-compile-multi --generate-hashes base --generate-hashes test --generate-hashes dev",
        "chmod 644 requirements/*.txt",
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

    requirement_files = ROOT_DIR.glob("requirements/**/*")
    current_user = os.getuid()
    current_group = os.getgid()
    for file in requirement_files:
        os.chown(file, current_user, current_group)


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
