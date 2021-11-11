from jobgraph.util.docker_registries import build_image_full_location


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
