from functools import wraps

from jobgraph.optimize import OptimizationStrategy, register_strategy
from jobgraph.util.memoize import memoize


@register_strategy("skip_if_cache_exists")
class GitlabCacheSearch(OptimizationStrategy):
    def should_remove_job(self, job, params, graph_config, arg):
        if not arg:
            return False

        return all(
            does_cache_exist(graph_config, cache["key"])
            for cache in job.actual_gitlab_ci_job["cache"]
        )


_registry_cache_type = {}


def register_cache_type(domain):
    def inner_function(func):
        if domain not in _registry_cache_type:
            _registry_cache_type[domain] = func

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return inner_function


@memoize
def does_cache_exist(graph_config, cache_path):
    cache_type = graph_config["cache"]["type"]
    try:
        does_cache_exist_func = _registry_cache_type[cache_type]
        return does_cache_exist_func(graph_config, cache_path)
    except KeyError:
        raise KeyError(f"Unknown cache type: {cache_type}")
