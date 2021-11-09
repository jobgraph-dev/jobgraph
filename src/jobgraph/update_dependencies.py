import os
import subprocess

from jobgraph.paths import PYTHON_VERSION_FILE, ROOT_DIR


def update_dependencies(options):
    _update_jobgraph_python_requirements()


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
