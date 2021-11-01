import os
import requests

from urllib.parse import unquote, urlparse


def extract_gitlab_instance_and_namespace_and_name(url):
    """Given an URL, return the instance domain name, repo name and the namespace it lives under.
    Args:
        url (str): The URL to the Gitlab repository
    Returns:
        str, str: the owner of the repository, the repository name
    """
    parsed_url = urlparse(url)
    domain_name = parsed_url.netloc

    path = unquote(parsed_url.path).lstrip("/")
    parts = path.split("/")
    repo_namespace = "/".join(parts[:-1])
    repo_name = parts[-1]

    return domain_name, repo_namespace, repo_name


# TODO Retry request
def get_container_registry_id(gitlab_domain_name, project_id, image_name):
    response = requests.get(
        f"https://{gitlab_domain_name}/api/v4/projects/{project_id}/registry/repositories",
        headers={
            "JOB-TOKEN": os.environ.get("CI_JOB_TOKEN"),
        },
    )
    response.raise_for_status()
    all_registries = response.json()

    matching_registries = [registry for registry in all_registries if registry["name"] == image_name]
    if len(matching_registries) == 0:
        raise ValueError(f'No container registry found for image "{image_name}"')
    elif len(matching_registries) > 1:
        raise IndexError(f'More than a single registry matched image "{image_name}"')

    return matching_registries[0]["id"]


# TODO Retry request
def get_container_registry_image_digest(gitlab_domain_name, project_id, image_name, image_tag):
    registry_id = get_container_registry_id(gitlab_domain_name, project_id, image_name)
    response = requests.get(
        f"https://{gitlab_domain_name}/api/v4/projects/{project_id}/registry/repositories/{registry_id}/tags/{image_tag}",
        headers={
            "JOB-TOKEN": os.environ.get("CI_JOB_TOKEN"),
        },
    )

    if response.status_code == 404:
        raise ValueError(f"No digest found for tag: {image_tag}")

    response.raise_for_status()

    return response.json()["digest"]