import os

import requests

from jobgraph.util.memoize import memoize

_DOCKER_IMAGE_DIGEST_METHOD = "@sha256:"
_DOCKER_DEFAULT_REGISTRY = "index.docker.io"
_AUTHENTICATION_CONFIG_PER_REGISTRY = {
    _DOCKER_DEFAULT_REGISTRY: {
        "endpoint": "https://auth.docker.io/token",
        "params": {
            "service": "registry.docker.io",
        },
    },
    # TODO: Support self-hosted gitlab instances.
    "registry.gitlab.com": {
        "endpoint": "https://gitlab.com/jwt/auth",
        "params": {
            "client_id": "docker",
            "offline_token": "true",
            "service": "container_registry",
        },
        "auth_env_variables": ("CI_REGISTRY_USER", "CI_REGISTRY_PASSWORD"),
    },
}


@memoize
def fetch_image_digest_from_registry(image_full_location):
    image_data = _parse_image_full_location(image_full_location)
    token = _get_container_registry_token(image_data)
    return _get_image_digest(image_data, token)


def _parse_image_full_location(image_full_location):
    image_parts = image_full_location.split(_DOCKER_IMAGE_DIGEST_METHOD)
    image_name_and_tag = image_parts[0]
    digest = (
        ""
        if len(image_parts) == 1
        else f"{_DOCKER_IMAGE_DIGEST_METHOD}{image_parts[1]}".lstrip("@")
    )

    image_name_and_tag_parts = image_name_and_tag.split(":")
    image_full_name = image_name_and_tag_parts[0]
    tag = (
        "latest" if len(image_name_and_tag_parts) == 1 else image_name_and_tag_parts[1]
    )

    image_full_name_parts = image_full_name.split("/")
    image_name = image_full_name_parts[-1]
    if len(image_full_name_parts) == 1:
        # it's an official image on Docker Hub
        registry = _DOCKER_DEFAULT_REGISTRY
        namespace = "library"
    else:
        if "." in image_full_name_parts[0]:
            registry = image_full_name_parts[0]
            namespace = "/".join(image_full_name_parts[1:-1])
        else:
            registry = _DOCKER_DEFAULT_REGISTRY
            namespace = "/".join(image_full_name_parts[0:-1])

    return {
        "digest": digest,
        "image_name": image_name.lower(),
        "namespace": namespace.lower(),
        "registry": registry.lower(),
        "tag": tag,
    }


def _get_container_registry_token(image_data):
    registry = image_data["registry"]
    auth_config = _AUTHENTICATION_CONFIG_PER_REGISTRY[registry]
    session = requests.Session()
    if auth_config.get("auth_env_variables"):
        for env_var_name in auth_config["auth_env_variables"]:
            if not os.environ.get(env_var_name):
                raise KeyError(
                    f'Please set environment variable "{env_var_name}" '
                    f"to let jobgraph authenticate to {registry}"
                )

        session.auth = tuple(
            os.environ[env_var] for env_var in auth_config["auth_env_variables"]
        )

    params = {
        "scope": f"repository:{image_data['namespace']}/{image_data['image_name']}:pull",
    }
    params |= auth_config.get("params", {})
    response = session.get(auth_config["endpoint"], params=params)
    response.raise_for_status()
    return response.json()["token"]


def _get_image_digest(image_data, token):
    url = f"https://{image_data['registry']}/v2/{image_data['namespace']}/{image_data['image_name']}/manifests/{image_data['tag']}"  # noqa E501
    response = requests.get(
        url,
        headers={
            "Accept": "application/vnd.docker.distribution.manifest.v2+json",
            "Authorization": f"Bearer {token}",
        },
    )

    if response.status_code == 404:
        full_location = build_image_full_location(image_data)
        raise ValueError(f"No digest found for: {full_location}")
    response.raise_for_status()

    return response.headers["Docker-Content-Digest"]


def set_digest(image_full_location, new_digest):
    image_data = _parse_image_full_location(image_full_location)
    image_data["digest"] = new_digest
    return build_image_full_location(image_data)


def build_image_full_location(image_data):
    registry = image_data["registry"]
    string = ""

    if registry != _DOCKER_DEFAULT_REGISTRY:
        string = f"{registry}/".lower()
    if registry != _DOCKER_DEFAULT_REGISTRY or (
        registry == _DOCKER_DEFAULT_REGISTRY and image_data["namespace"] != "library"
    ):
        string = f"{string}{image_data['namespace']}/".lower()

    string = f"{string}{image_data['image_name']}".lower()

    if image_data["tag"] != "latest":
        string = f"{string}:{image_data['tag']}"
    if image_data.get("digest"):
        string = f"{string}@{image_data['digest']}"

    return string
