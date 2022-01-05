from jobgraph.util.docker_registries import (
    build_image_full_location,
    get_container_registry_session,
    get_image_digest,
    register_docker_registry_domain,
)


@register_docker_registry_domain("registry.gitlab.com")
def fetch_image_digest_from_gitlab_com(image_data):
    session = get_container_registry_session(
        image_data,
        {
            "endpoint": "https://gitlab.com/jwt/auth",
            "params": {
                "client_id": "docker",
                "offline_token": "true",
                "service": "container_registry",
            },
            "auth_env_variables": ("CI_REGISTRY_USER", "CI_REGISTRY_PASSWORD"),
        },
    )
    return get_image_digest(image_data, session)


def get_image_full_location(
    gitlab_domain_name,
    project_namespace,
    project_name,
    image_name,
    image_tag,
):
    return build_image_full_location(
        {
            "registry": f"registry.{gitlab_domain_name}",
            "namespace": f"{project_namespace}/{project_name}",
            "image_name": image_name,
            "tag": image_tag,
        }
    )
