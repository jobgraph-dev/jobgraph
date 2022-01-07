from jobgraph.optimize import OptimizationStrategy, register_strategy
from jobgraph.util.docker_registries import fetch_image_digest_from_registry


@register_strategy("skip_if_on_docker_registry")
class DockerRegistrySearch(OptimizationStrategy):
    def should_remove_job(self, job, params, graph_config, arg):
        if not arg:
            return False

        try:
            fetch_image_digest_from_registry(
                job.attributes["docker_image_full_location"]
            )
            return True
        except ValueError:
            return False
