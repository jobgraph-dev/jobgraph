from pathlib import Path

from voluptuous import Any, Optional, Required

from jobgraph.transforms.base import TransformSequence
from jobgraph.util.hash import hash_paths
from jobgraph.util.schema import (
    cache_def,
    gitlab_ci_job_input,
    optionally_keyed_by,
    resolve_keyed_by,
)

cache_def_input = {
    **cache_def,
    **{
        Required("key"): Any(
            str,
            {
                Required("files"): [str],
                Optional("prefix"): optionally_keyed_by("head_ref_protection", str),
            },
        ),
    },
}


cache_schema = gitlab_ci_job_input.extend(
    {
        Required("cache"): cache_def_input,
        Required("name"): str,
        Optional("label"): str,
    }
)

transforms = TransformSequence()

transforms.add_validate(cache_schema)


@transforms.add
def resolve_keyed_variables(config, jobs):
    for job in jobs:
        for key in ("cache.key.prefix",):
            resolve_keyed_by(
                job,
                key,
                item_name=job["name"],
                **{
                    "head_ref_protection": config.params["head_ref_protection"],
                },
            )

        yield job


@transforms.add
def set_head_ref_in_cache_prefix(config, jobs):
    for job in jobs:
        prefix = job["cache"]["key"].get("prefix", "")
        if prefix:
            job["cache"]["key"]["prefix"] = prefix.format(
                head_ref=config.params["head_ref"]
            )
        yield job


@transforms.add
def set_optimization(config, jobs):
    for job in jobs:
        job.setdefault("optimization", {}).setdefault("skip_if_cache_exists", True)

        cache = job["cache"]
        key = cache.get("key", {})
        repo_root = Path(config.graph_config.root_dir).parent
        files_hashes = hash_paths(str(repo_root), key.get("files", []))

        prefix = job["cache"]["key"].get("prefix", "")
        cache["key"] = f"{prefix}/{files_hashes}" if prefix else files_hashes

        yield job
