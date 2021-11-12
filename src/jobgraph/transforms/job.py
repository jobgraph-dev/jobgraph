# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
These transformations take a job description and turn it into a Gitlab CI
job definition (along with attributes, label, etc.).  The input to these
transformations is generic to any kind of job, but abstracts away some of the
complexities of runner implementations.
"""

from copy import copy

from voluptuous import All, Any, NotIn, Optional, Required

from jobgraph import MAX_DEPENDENCIES
from jobgraph.transforms.base import TransformSequence
from jobgraph.util.schema import Schema, taskref_or_string, validate_schema

from ..util import docker as dockerutil
from ..util.runners import get_runner_tag

# A job description is a general description of a JobGrab job
job_description_schema = Schema(
    {
        Required("label"): str,
        Required("description"): str,
        Optional("attributes"): {str: object},
        # relative path (from config.path) to the file this job was defined in
        Optional("job-from"): str,
        # dependencies of this job, keyed by name; these are passed through
        # verbatim and subject to the interpretation of the Job's get_dependencies
        # method.
        Optional("dependencies"): {
            All(
                str,
                NotIn(
                    ["self", "decision"],
                    "Can't use 'self` or 'decision' as depdency names.",
                ),
            ): object,
        },
        Required("image"): Any(
            # strings are now allowed because we want to keep track of external
            # images in config.yml
            #
            # an in-tree generated docker image (from `gitlab-ci/docker/<name>`)
            {"in-tree": str},
            {"docker-image-reference": str},
        ),
        Optional("run-on-pipeline-sources"): [str],
        Optional("run-on-git-branches"): [str],
        # The `always-target` attribute will cause the job to be included in the
        # target_job_graph regardless of filtering. Jobs included in this manner
        # will be candidates for optimization even when `optimize_target_jobs` is
        # False, unless the job was also explicitly chosen by the target_jobs
        # method.
        Required("always-target"): bool,
        # Optimization to perform on this job during the optimization phase.
        # Optimizations are defined in gitlab-ci/jobgraph/optimize.py.
        Required("optimization"): Any(dict, None),
        # the runner-alias for the job. Will be substituted into an actual Gitlab
        # CI tag.
        "runner-alias": str,
        Required("script"): Any(
            taskref_or_string,
            [taskref_or_string],
        ),
        Optional("timeout"): str,
        Optional("variables"): dict,
    }
)


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
                docker_image_job = "build-docker-image-" + image["in-tree"]
                job.setdefault("dependencies", {})["docker-image"] = docker_image_job

                image = {"docker-image-reference": "<docker-image>"}

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
        job.setdefault("optimization", None)

        yield job


@transforms.add
def job_name_from_label(config, jobs):
    for job in jobs:
        if "label" not in job:
            if "name" not in job:
                raise Exception("job has neither a name nor a label")
            job["label"] = f"{config.kind}-{job['name']}"
        if job.get("name"):
            del job["name"]
        yield job


@transforms.add
def validate(config, jobs):
    for job in jobs:
        validate_schema(
            job_description_schema,
            job,
            f"In job {job.get('label', '?no-label?')!r}:",
        )
        yield job


@transforms.add
def build_job(config, jobs):
    for job in jobs:
        level = str(config.params["level"])

        runner_tag = get_runner_tag(
            config.graph_config,
            job["runner-alias"],
            level,
        )

        job_def = copy(config.graph_config["job-defaults"])
        job_def["tags"] = [runner_tag]
        job_def["script"] = job["script"]
        for key in ("retry", "timeout", "variables"):
            if job.get(key):
                job_def[key] = job[key]

        attributes = job.get("attributes", {})
        attributes["run_on_pipeline_sources"] = job.get(
            "run-on-pipeline-sources", ["all"]
        )
        attributes["run_on_git_branches"] = job.get("run-on-git-branches", ["all"])
        attributes["always_target"] = job["always-target"]

        yield {
            "label": job["label"],
            "description": job["description"],
            "actual_gitlab_ci_job": job_def,
            "dependencies": job.get("dependencies", {}),
            "attributes": attributes,
            "optimization": job.get("optimization", None),
        }


@transforms.add
def check_job_dependencies(config, jobs):
    """Ensures that jobs don't have more than 50 dependencies."""
    for job in jobs:
        if len(job["dependencies"]) > MAX_DEPENDENCIES:
            raise Exception(
                f"job {config.kind}/{job['label']} has too many dependencies "
                f"({len(job['dependencies'])} > {MAX_DEPENDENCIES})"
            )
        yield job
