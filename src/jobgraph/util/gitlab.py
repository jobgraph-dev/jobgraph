import os
import requests

from urllib.parse import unquote, urlparse

from jobgraph.util.memoize import memoize


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
@memoize
def get_container_registry_image_digest(gitlab_domain_name, project_namespace, project_name, image_name, image_tag):
    token = _get_container_registry_token(gitlab_domain_name, project_namespace, project_name, image_name)

    response = requests.get(
        f"https://registry.{gitlab_domain_name}/v2/{project_namespace}/{project_name}/{image_name}/manifests/{image_tag}",
        headers={
            "Accept": "application/vnd.docker.distribution.manifest.v2+json",
            "Authorization": f"Bearer {token}",
        }
    )
    if response.status_code == 404:
        raise ValueError(f"No digest found for tag: {image_tag}")

    response.raise_for_status()
    return response.json()["config"]["digest"]


def _get_container_registry_token(gitlab_domain_name, project_namespace, project_name, image_name):
    session = requests.Session()
    session.auth = (os.environ["CI_REGISTRY_USER"], os.environ["CI_REGISTRY_PASSWORD"])

    response = session.get(f"https://{gitlab_domain_name}/jwt/auth?client_id=docker&offline_token=true&service=container_registry")
    response.raise_for_status()
    return response.json()["token"]
