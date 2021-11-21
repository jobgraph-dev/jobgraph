# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
These transformations take a job description and turn it into a Gitlab CI
job definition (along with attributes, label, etc.).  The input to these
transformations is generic to any kind of job, but abstracts away some of the
complexities of runner implementations.
"""

from copy import copy, deepcopy

from deepmerge import always_merger

from jobgraph import MAX_DEPENDENCIES
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
            if "in-tree" in image:
                name = image["in-tree"]
                docker_image_job = image["in-tree"]
                job.setdefault("dependencies", {})["docker-image"] = docker_image_job

                job["image"] = {"docker-image-reference": "<docker-image>"}

                # Find VOLUME in Dockerfile.
                volumes = dockerutil.parse_volumes(name)
                if volumes:
                    raise Exception("volumes defined in Dockerfiles are not supported.")
            elif "docker-image-reference" in image:
                # Nothing to do, this will get resolved in the optimization phase
                pass
            else:
                raise Exception("unknown docker image type")

        yield job


@transforms.add
def set_defaults(config, jobs):
    for job in jobs:
        job.setdefault("always-target", False)
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
        job_dependencies = job.pop("dependencies", {})
        job_description = job.pop("description")
        job_optimization = job.pop("optimization")
        runner_alias = job.pop("runner-alias")
        job.pop("job-from", None)

        attributes = job.pop("attributes", {})
        attributes["run_on_pipeline_sources"] = job.pop(
            "run-on-pipeline-sources", ["push"]
        )
        attributes["run_on_git_branches"] = job.pop("run-on-git-branches", ["all"])
        attributes["always_target"] = job.pop("always-target")

        actual_gitlab_ci_job = always_merger.merge(
            deepcopy(config.graph_config["job-defaults"]), job
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
            "dependencies": job_dependencies,
            "attributes": attributes,
            "optimization": job_optimization,
        }


@transforms.add
def check_job_dependencies(config, jobs):
    """Ensures that jobs don't have more than 50 dependencies."""
    for job in jobs:
        if len(job["dependencies"]) > MAX_DEPENDENCIES:
            raise Exception(
                f"job {config.stage}/{job['label']} has too many dependencies "
                f"({len(job['dependencies'])} > {MAX_DEPENDENCIES})"
            )
        yield job
