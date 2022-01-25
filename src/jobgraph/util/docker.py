import hashlib
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

import requests_unixsocket
from dockerfile_parse import DockerfileParser

from jobgraph.config import DEFAULT_ROOT_DIR
from jobgraph.parameters import get_repo
from jobgraph.util.memoize import memoize

from .yaml import load_yaml

IMAGE_DIR = os.path.join(".", "gitlab-ci", "docker")


def docker_url(path, **kwargs):
    docker_socket = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")
    return urllib.parse.urlunparse(
        (
            "http+unix",
            urllib.parse.quote(docker_socket, safe=""),
            path,
            "",
            urllib.parse.urlencode(kwargs),
            "",
        )
    )


def post_to_docker(tar, api_path, **kwargs):
    """POSTs a tar file to a given docker API path.

    The tar argument can be anything that can be passed to requests.post()
    as data (e.g. iterator or file object).
    The extra keyword arguments are passed as arguments to the docker API.
    """
    req = requests_unixsocket.Session().post(
        docker_url(api_path, **kwargs),
        data=tar,
        stream=True,
        headers={"Content-Type": "application/x-tar"},
    )
    if req.status_code != 200:
        message = req.json().get("message")
        if not message:
            message = f"docker API returned HTTP code {req.status_code}"
        raise Exception(message)
    status_line = {}

    buf = b""
    for content in req.iter_content(chunk_size=None):
        if not content:
            continue
        # Sometimes, a chunk of content is not a complete json, so we cumulate
        # with leftovers from previous iterations.
        buf += content
        try:
            data = json.loads(buf)
        except Exception:
            continue
        buf = b""
        # data is sometimes an empty dict.
        if not data:
            continue
        # Mimick how docker itself presents the output. This code was tested
        # with API version 1.18 and 1.26.
        if "status" in data:
            if "id" in data:
                if sys.stderr.isatty():
                    total_lines = len(status_line)
                    line = status_line.setdefault(data["id"], total_lines)
                    n = total_lines - line
                    if n > 0:
                        # Move the cursor up n lines.
                        sys.stderr.write(f"\033[{n}A")
                    # Clear line and move the cursor to the beginning of it.
                    sys.stderr.write("\033[2K\r")
                    sys.stderr.write(
                        f"{data['id']}: {data['status']} {data.get('progress', '')}\n"
                    )
                    if n > 1:
                        # Move the cursor down n - 1 lines, which, considering
                        # the carriage return on the last write, gets us back
                        # where we started.
                        sys.stderr.write(f"\033[{n - 1}B")
                else:
                    status = status_line.get(data["id"])
                    # Only print status changes.
                    if status != data["status"]:
                        sys.stderr.write(f"{data['id']}: {data['status']}\n")
                        status_line[data["id"]] = data["status"]
            else:
                status_line = {}
                sys.stderr.write(f"{data['status']}\n")
        elif "stream" in data:
            sys.stderr.write(data["stream"])
        elif "aux" in data:
            sys.stderr.write(repr(data["aux"]))
        elif "error" in data:
            sys.stderr.write(f"{data['error']}\n")
            # Sadly, docker doesn't give more than a plain string for errors,
            # so the best we can do to propagate the error code from the command
            # that failed is to parse the error message...
            errcode = 1
            m = re.search(r"returned a non-zero code: (\d+)", data["error"])
            if m:
                errcode = int(m.group(1))
            sys.exit(errcode)
        else:
            raise NotImplementedError(repr(data))
        sys.stderr.flush()


def generate_context_hash(
    docker_context_root, image_path, args=None, dind_image_full_location=None
):
    copied_files = _get_tracked_copied_files_to_docker_image(
        docker_context_root, image_path, args
    )
    return stream_context_tar(
        docker_context_root,
        image_path,
        copied_files=copied_files,
        args=args,
        dind_image_full_location=dind_image_full_location,
    )


def _get_tracked_copied_files_to_docker_image(docker_context_root, image_path, args):
    all_copied_files = _get_all_copied_files_to_docker_image(
        docker_context_root, image_path, args
    )
    tracked_files = [
        docker_context_root / file_path
        for file_path in get_repo(docker_context_root).tracked_files
    ]
    return [file for file in all_copied_files if file in tracked_files]


def _get_all_copied_files_to_docker_image(docker_context_root, image_path, args):
    # /!\ `env_replace` doesn't evaluate environment variables when calling
    # docker_file.structure. As of DockerfileParser 1.2.0, there is no other
    # way than substituing environment variables ourselves.
    docker_file = DockerfileParser(path=image_path, build_args=args, cache_content=True)

    all_copied_files = set()
    env_variables = {**docker_file.args, **docker_file.envs}

    for instruction in docker_file.structure:
        if instruction.get("instruction") not in ("ADD", "COPY"):
            continue

        file_arguments = instruction["value"].split(" ")
        # The last file argument is always the destination in the docker
        # image. We just want the source files/dirs.
        for file_argument in file_arguments[:-1]:
            # `--from` copies files from another container, these files
            # are not part of the root context
            if file_argument.startswith("--from"):
                break

            if file_argument.startswith("--chown"):
                continue

            # /!\ FIXME: Some environment variables may have different
            # values along the dockerfile. Here we're only taking the
            # last known value
            for env_key, env_value in env_variables.items():
                file_argument = file_argument.replace(f"${env_key}", env_value)
                file_argument = file_argument.replace(f"${{{env_key}}}", env_value)

            file_argument = file_argument.strip("'")
            file_argument = file_argument.strip('"')

            for path in Path(docker_context_root).glob(file_argument):
                if not path.exists():
                    raise ValueError(f"path does not exist: {path}")

                if path.is_file():
                    all_copied_files.add(path)
                    continue

                if path.is_dir():
                    for file_in_dir in path.glob("**/*"):
                        if file_in_dir.is_file():
                            all_copied_files.add(file_in_dir)
                    continue

                raise ValueError(f"Unsupported path: {path}")

    return all_copied_files


def stream_context_tar(
    docker_context_root,
    image_path,
    copied_files=None,
    args=None,
    dind_image_full_location=None,
):
    args = {} if args is None else args
    copied_files = [] if copied_files is None else copied_files
    copied_files.append(Path(image_path))
    docker_context_root = Path(docker_context_root).resolve()

    hash = hashlib.sha256()
    for file_path in sorted(copied_files):
        if not file_path.is_absolute():
            file_path = docker_context_root / file_path

        elif not file_path.is_relative_to(docker_context_root):
            raise ValueError(
                f'File "{file_path}" is not within the docker context root '
                '"{docker_context_root}"'
            )

        if not file_path.is_file():
            raise ValueError(f'Path "{file_path}" must be a file')

        with open(file_path, "rb") as f:
            hash.update(f.read())

    for arg_name, arg_value in args.items():
        hash.update(f"ARG {arg_name}={arg_value}".encode())

    if dind_image_full_location:
        hash.update(f"DOCKER_IN_DOCKER {dind_image_full_location}".encode())

    return hash.hexdigest()


@memoize
def image_paths():
    """Return a map of image name to paths containing their Dockerfile."""
    config = load_yaml(DEFAULT_ROOT_DIR, "docker_image", "stage.yml")
    return {
        k: os.path.join(IMAGE_DIR, v.get("definition", k))
        for k, v in config["jobs"].items()
    }


def image_path(name):
    paths = image_paths()
    if name in paths:
        return paths[name]
    return os.path.join(IMAGE_DIR, name)


@memoize
def parse_volumes(image):
    """Parse VOLUME entries from a Dockerfile for an image."""
    volumes = set()

    path = image_path(image)

    with open(os.path.join(path, "Dockerfile"), "rb") as fh:
        for line in fh:
            line = line.strip()
            # We assume VOLUME definitions don't use %ARGS.
            if not line.startswith(b"VOLUME "):
                continue

            v = line.split(None, 1)[1]
            if v.startswith(b"["):
                raise ValueError(
                    "cannot parse array syntax for VOLUME; "
                    "convert to multiple entries"
                )

            volumes |= {volume.decode("utf-8") for volume in v.split()}

    return volumes
