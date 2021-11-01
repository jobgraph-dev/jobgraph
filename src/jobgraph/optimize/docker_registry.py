import requests

from jobgraph.util.gitlab import get_container_registry_image_digest
from jobgraph.optimize import OptimizationStrategy, register_strategy


@register_strategy("skip-if-on-gitlab-container-registry")
class GitlabContainerRegistrySearch(OptimizationStrategy):

    def should_remove_task(self, task, params, arg):
        image_name = task.attributes["image_name"]
        image_tag = task.attributes["context_hash"]
        head_url = params["head_repository"]

        try:
            get_container_registry_image_digest(head_url, image_name, image_tag)
            return True
        except ValueError:
            return False

    def should_replace_task(self, *args):
        return False
