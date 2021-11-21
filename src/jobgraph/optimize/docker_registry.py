from jobgraph.optimize import OptimizationStrategy, register_strategy
from jobgraph.util.docker_registries import fetch_image_digest_from_registry
from jobgraph.util.docker_registries.gitlab import get_image_full_location
from jobgraph.util.gitlab import extract_gitlab_instance_and_namespace_and_name


@register_strategy("skip_if_on_gitlab_container_registry")
class GitlabContainerRegistrySearch(OptimizationStrategy):
    def should_remove_job(self, job, params, arg):
        if not arg:
            return False

        image_name = job.attributes["image_name"]
        image_tag = job.attributes["context_hash"]
        (
            gitlab_domain_name,
            project_namespace,
            project_name,
        ) = extract_gitlab_instance_and_namespace_and_name(params["head_repository"])
        image_full_location = get_image_full_location(
            gitlab_domain_name,
            project_namespace,
            project_name,
            image_name,
            image_tag,
        )

        try:
            fetch_image_digest_from_registry(image_full_location)
            return True
        except ValueError:
            return False
