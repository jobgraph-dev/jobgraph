from urllib.parse import unquote, urlparse

GITLAB_DEFAULT_ROOT_URL = "https://gitlab.com"


def extract_gitlab_instance_and_namespace_and_name(url):
    """Given an URL, return the instance domain name, repo name and the
    namespace it lives under.
    Args:
        url (str): The URL to the Gitlab repository
    Returns:
        str, str: the owner of the repository, the repository name
    """
    https_url = convert_ssh_url_into_https(url)
    parsed_url = urlparse(https_url)
    domain_name = parsed_url.netloc

    path = unquote(parsed_url.path).lstrip("/")
    parts = path.split("/")
    repo_namespace = "/".join(parts[:-1])
    repo_name = parts[-1]

    return domain_name, repo_namespace, repo_name


def convert_ssh_url_into_https(url):
    new_url = url.replace("git@", "https://")
    new_url = new_url.replace("gitlab.com:", "gitlab.com/")
    if new_url.endswith(".git"):
        new_url = new_url[: -len(".git")]

    return new_url
