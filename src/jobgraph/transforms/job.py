"""
These transformations take a job description and turn it into a Gitlab CI
job definition (along with attributes, label, etc.).  The input to these
transformations is generic to any kind of job, but abstracts away some of the
complexities of runner implementations.
"""

from copy import copy, deepcopy

from deepmerge import always_merger

from jobgraph import MAX_UPSTREAM_DEPENDENCIES
from jobgraph.transforms.base import TransformSequence
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
