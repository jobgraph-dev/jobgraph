import requests

from jobgraph.util.gitlab import get_container_registry_image_digest, extract_gitlab_instance_and_namespace_and_name
from jobgraph.optimize import OptimizationStrategy, register_strategy


@register_strategy("skip-if-on-gitlab-container-registry")
class GitlabContainerRegistrySearch(OptimizationStrategy):

    def should_remove_task(self, task, params, arg):
        image_name = task.attributes["image_name"]
        image_tag = task.attributes["context_hash"]
        project_id = params["project_id"]

        gitlab_domain_name, _, _ = extract_gitlab_instance_and_namespace_and_name(params["head_repository"])

        try:
            get_container_registry_image_digest(gitlab_domain_name, project_id, image_name, image_tag)
            return True
        except ValueError:
            return False

    def should_replace_task(self, *args):
        return False
