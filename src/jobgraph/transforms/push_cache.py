from pathlib import Path

from voluptuous import Optional, Required

from jobgraph.transforms.base import TransformSequence
from jobgraph.util.hash import hash_paths
from jobgraph.util.schema import gitlab_ci_job_input

cache_def_input = {
    Required("key_files"): [str],
    Required("paths"): [str],
}


cache_schema = gitlab_ci_job_input.extend(
    {
        Required("push_caches"): [cache_def_input],
        Required("name"): str,
        Optional("label"): str,
    }
)

transforms = TransformSequence()

transforms.add_validate(cache_schema)


@transforms.add
def set_gitlab_cache_definition(config, jobs):
    repo_root = Path(config.graph_config.root_dir).parent

    for job in jobs:
        actual_caches = job.setdefault("cache", [])
        push_caches = job.pop("push_caches", [])

        for push_cache in push_caches:
            files_hashes = hash_paths(str(repo_root), push_cache["key_files"])
            prefix = (
                config.params["head_ref"]
                if config.params["head_ref_protection"] == "protected"
                else "unprotected-branches"
            )

            actual_caches.append(
                {
                    "key": f"{prefix}-{job['name']}-{files_hashes}",
                    "paths": push_cache["paths"],
                    "policy": "push",
                }
            )

        job.setdefault("optimization", {}).setdefault("skip_if_cache_exists", True)

        yield job
