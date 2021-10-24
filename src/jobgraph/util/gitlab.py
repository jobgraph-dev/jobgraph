
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
    repo_owner = "/".join(parts[:-1])
    repo_name = parts[-1]

    return domain_name, repo_owner, repo_name


def _strip_trailing_dot_git(url):
    if url.endswith(".git"):
        url = url[: -len(".git")]
    return url
