"""
These transformations take a job description and turn it into a Gitlab CI
job definition (along with attributes, label, etc.).  The input to these
transformations is generic to any kind of job, but abstracts away some of the
complexities of runner implementations.
"""

import hashlib
from copy import copy, deepcopy
from pathlib import Path

from deepmerge import always_merger

from jobgraph import MAX_UPSTREAM_DEPENDENCIES
from jobgraph.transforms.base import TransformSequence
from jobgraph.util.hash import hash_paths
from jobgraph.util.schema import gitlab_ci_job_input, validate_schema

from ..util import docker as dockerutil
from ..util.runners import get_runner_tag


def get_branch_rev(config):
    return config.params["head_rev"]


transforms = TransformSequence()


@transforms.add
def build_docker_runner_payload(config, jobs):
    for job in jobs:
        image = job["image"]
        if isinstance(image, dict):
            if "in_tree" in image:
                name = image["in_tree"]
                docker_image_job = image["in_tree"]
                job.setdefault("upstream_dependencies", {})[
                    "docker_image"
                ] = docker_image_job

                job["image"] = {"docker_image_reference": "<docker_image>"}

                # Find VOLUME in Dockerfile.
                volumes = dockerutil.parse_volumes(name)
                if volumes:
                    raise Exception("volumes defined in Dockerfiles are not supported.")
            elif "docker_image_reference" in image:
                # Nothing to do, this will get resolved in the optimization phase
                pass
            else:
                raise Exception("unknown docker image type")

        yield job


@transforms.add
def set_defaults(config, jobs):
    for job in jobs:
        job.setdefault("always_target", False)
        job.setdefault("optimization", {})

        variables = job.setdefault("variables", {})
        # Let jobs automatically retry if they fail cloning/fetching the repo.
        # It's a Gitlab variable.
        # https://docs.gitlab.com/ee/ci/runners/configure_runners.html
        variables.setdefault("GET_SOURCES_ATTEMPTS", 3)

        yield job


@transforms.add
def job_name_from_label(config, jobs):
    for job in jobs:
        if "label" not in job:
            if "name" not in job:
                raise Exception("job has neither a name nor a label")
            job["label"] = job["name"]
        if job.get("name"):
            del job["name"]
        yield job


@transforms.add
def validate(config, jobs):
    for job in jobs:
        validate_schema(
            gitlab_ci_job_input,
            job,
            f"In job {job['label']}:",
        )
        yield job


@transforms.add
def set_decision_needs(config, jobs):
    for job in jobs:
        if job.pop("download_artifacts_from_decision_job", False):
            needs = job.setdefault("needs", [])
            needs.append(
                {
                    "pipeline": config.params["pipeline_id"],
                    "job": "decision",
                }
            )
        yield job


@transforms.add
def build_pull_cache_payload(config, jobs):
    for job in jobs:
        upstream_cache_jobs = job.get("upstream_cache_jobs", [])
        pull_caches = job.setdefault("cache", [])
        upstream_deps = job.setdefault("upstream_dependencies", {})

        for cache_job in upstream_cache_jobs:
            upstream_deps[f"cache_{cache_job.label}"] = cache_job.label

            all_caches = cache_job.actual_gitlab_ci_job["cache"]
            if type(all_caches) == dict:
                all_caches = [all_caches]

            push_caches = [
                cache
                for cache in all_caches
                if "push" in cache.get("policy", "pull-push")
            ]
            for push_cache in push_caches:
                pull_caches.append(
                    {
                        "key": push_cache["key"],
                        "paths": push_cache["paths"],
                        "policy": "pull",
                    }
                )

        yield job


@transforms.add
def build_push_cache_payload(config, jobs):
    repo_root = Path(config.graph_config.root_dir).parent

    for job in jobs:
        upstream_cache_jobs = job.pop("upstream_cache_jobs", [])
        push_caches = job.pop("push_caches", [])
        actual_caches_configuration = job.setdefault("cache", [])

        for push_cache in push_caches:
            cache_hash = _build_push_cache_hash(
                repo_root, push_cache["key_files"], upstream_cache_jobs
            )

            prefix = (
                config.params["head_ref"]
                if config.params["head_ref_protection"] == "protected"
                else "unprotected-branches"
            )

            actual_caches_configuration.append(
                {
                    "key": f"{prefix}-{job['label']}-{cache_hash}",
                    "paths": push_cache["paths"],
                    "policy": "push",
                }
            )

            attributes_push_cache = job.setdefault("attributes", {}).setdefault(
                "push_caches_hashes", []
            )
            attributes_push_cache.append(cache_hash)

            job.setdefault("optimization", {}).setdefault("skip_if_cache_exists", True)

        yield job


def _build_push_cache_hash(repo_root, key_files, upstream_cache_jobs):
    hash = hashlib.sha256()

    files_hashes = hash_paths(repo_root, key_files)
    hash.update(f"files {files_hashes}".encode())

    for cache_job in upstream_cache_jobs:
        for push_cache_hash in cache_job.attributes["push_caches_hashes"]:
            hash.update(f"{cache_job.label} {push_cache_hash}".encode())

    return hash.hexdigest()


@transforms.add
def set_cache_default_variables(config, jobs):
    for job in jobs:
        if job.get("cache"):
            variables = job.setdefault("variables", {})
            # Gitlab CI specific variables. They're all documented at
            # https://docs.gitlab.com/ee/ci/runners/configure_runners.html

            # Storage vs compute. Usually storage is cheaper in the cloud.
            variables.setdefault("CACHE_COMPRESSION_LEVEL", "fastest")
            # We aim to have small and unitary jobs. We shouldn't pull
            # caches that are too big so let's aim for short timeout
            # by default.
            variables.setdefault("CACHE_REQUEST_TIMEOUT", "2 minutes")
            # Let's enable a retry mechanism (Gitlab Runners don't by default)
            variables.setdefault("RESTORE_CACHE_ATTEMPTS", 3)
            variables.setdefault("TRANSFER_METER_FREQUENCY", "5s")

        yield job


@transforms.add
def set_artifacts_default_variables(config, jobs):
    for job in jobs:
        if job.get("artifacts"):
            # Same rationale as cache. Variables are documented at the same place.
            variables = job.setdefault("variables", {})
            variables.setdefault("ARTIFACT_COMPRESSION_LEVEL", "fastest")
            variables.setdefault("ARTIFACT_DOWNLOAD_ATTEMPTS", 3)
            variables.setdefault("TRANSFER_METER_FREQUENCY", "5s")

        yield job


@transforms.add
def build_job(config, jobs):
    for job in jobs:
        # /!\ We make a copy of job because some transforms (like the docker_image one)
        # expect job to still contain some keys (like "label").
        # This behavior is explained by the fact transforms yield each job individually,
        # meaning the first job gets through the whole transform chain before the next
        # one is processed.
        job = copy(job)

        job_label = job.pop("label")
        job_upstream_dependencies = job.pop("upstream_dependencies", {})
        job_description = job.pop("description")
        job_optimization = job.pop("optimization")
        runner_alias = job.pop("runner_alias")
        job.pop("job_from", None)

        attributes = job.pop("attributes", {})
        attributes["always_target"] = job.pop("always_target")
        attributes["run_on_pipeline_sources"] = job.pop(
            "run_on_pipeline_sources", ["push", "web"]
        )
        attributes["run_on_git_branches"] = job.pop("run_on_git_branches", ["all"])
        schedules = job.pop("schedules", {})
        if schedules:
            attributes["schedules"] = schedules
            attributes["run_on_pipeline_sources"].append("schedule")

        actual_gitlab_ci_job = always_merger.merge(
            deepcopy(config.graph_config["job_defaults"]), job
        )

        head_ref_protection = config.params["head_ref_protection"]
        runner_tag = get_runner_tag(
            config.graph_config,
            runner_alias,
            head_ref_protection,
        )
        actual_gitlab_ci_job["tags"] = [runner_tag]

        yield {
            "label": job_label,
            "description": job_description,
            "actual_gitlab_ci_job": actual_gitlab_ci_job,
            "upstream_dependencies": job_upstream_dependencies,
            "attributes": attributes,
            "optimization": job_optimization,
        }


@transforms.add
def check_job_dependencies(config, jobs):
    """Ensures that jobs don't have more than 50 upstream dependencies."""
    for job in jobs:
        if len(job["upstream_dependencies"]) > MAX_UPSTREAM_DEPENDENCIES:
            raise Exception(
                f"job {config.stage}/{job['label']} has too many dependencies "
                f"({len(job['upstream_dependencies'])} > {MAX_UPSTREAM_DEPENDENCIES})"
            )
        yield job
