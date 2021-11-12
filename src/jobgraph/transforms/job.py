# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
These transformations take a job description and turn it into a Gitlab CI
job definition (along with attributes, label, etc.).  The input to these
transformations is generic to any kind of job, but abstracts away some of the
complexities of runner implementations.
"""


import attr
from voluptuous import All, Any, Extra, NotIn, Optional, Required

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
        # information specific to the runner implementation that will run this job
        Optional("runner"): {
            Required("implementation"): str,
            Extra: object,
        },
    }
)


def get_branch_rev(config):
    return config.params["head_rev"]


# define a collection of payload builders, depending on the runner implementation
payload_builders = {}


@attr.s(frozen=True)
class PayloadBuilder:
    schema = attr.ib(type=Schema)
    builder = attr.ib()


def payload_builder(name, schema):
    schema = Schema({Required("implementation"): name, Optional("os"): str}).extend(
        schema
    )

    def wrap(func):
        payload_builders[name] = PayloadBuilder(schema, func)
        return func

    return wrap


@payload_builder(
    "kubernetes",
    schema={
        Optional("os"): "linux",
        # For jobs that will run in kubernetes, this is the name of the docker
        # image or in-tree docker image to run the job on.  If in-tree, then a
        # dependency will be created automatically.  This is generally
        # `desktop-test`, or an image that acts an awful lot like it.
        Required("docker-image"): Any(
            # strings are now allowed because we want to keep track of external
            # images in config.yml
            #
            # an in-tree generated docker image (from `gitlab-ci/docker/<name>`)
            {"in-tree": str},
            {"docker-image-reference": str},
        ),
        # runner features that should be enabled
        Required("chain-of-trust"): bool,
        Required("docker-in-docker"): bool,  # (aka 'dind')
        # caches to set up for the job
        Optional("caches"): [
            {
                # only one type is supported by any of the runners right now
                "type": "persistent",
                # name of the cache, allowing re-use by subsequent jobs naming the
                # same cache
                "name": str,
                # location in the job image where the cache will be mounted
                "mount-point": str,
                # Whether the cache is not used in untrusted environments
                # (like the Try repo).
                Optional("skip-untrusted"): bool,
            }
        ],
        # artifacts to extract from the job image after completion
        Optional("artifacts"): [
            {
                # type of artifact -- simple file, or recursive directory
                "type": Any("file", "directory"),
                # job image path from which to read artifact
                "path": str,
                # name of the produced artifact (root of the names for
                # type=directory)
                "name": str,
            }
        ],
        # environment variables
        Required("env"): {str: taskref_or_string},
        # the command to run; if not given, kubernetes will default to the
        # command in the docker image
        Optional("command"): taskref_or_string,
        # the maximum time to run, in seconds
        Required("max-run-time"): int,
        # the exit status code(s) that indicates the job should be retried
        Optional("retry-exit-status"): [int],
        # the exit status code(s) that indicates the caches used by the job
        # should be purged
        Optional("purge-caches-exit-status"): [int],
        # Wether any artifacts are assigned to this runner
        Optional("skip-artifacts"): bool,
    },
)
def build_docker_runner_payload(config, job, job_def):
    runner = job["runner"]
    level = int(config.params["level"])

    image = runner["docker-image"]
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

    features = {}

    if runner.get("docker-in-docker"):
        job_def["services"] = [
            config.graph_config["jobgraph"]["external-docker-images"][
                "docker-in-docker"
            ]
        ]

    capabilities = {}

    job_def["image"] = image
    job_def["variables"] = runner["env"]

    if "command" in runner:
        job_def["script"] = [runner["command"]]

    if "max-run-time" in runner:
        job_def["timeout"] = f'{runner["max-run-time"]} seconds'

    payload = {}

    if "artifacts" in runner:
        job_def["artifacts"] = {
            "expire_in": "3 months",  # TODO: Parametrize
            "paths": [artifact["path"] for artifact in runner["artifacts"]],
            "public": False,  # TODO: Parametrize
            "reports": {},  # TODO: Support different types of reports
        }

    if "caches" in runner:
        caches = {}
        cache_version = "v3"
        suffix = cache_version

        skip_untrusted = config.params.is_try() or level == 1

        for cache in runner["caches"]:
            # Some caches aren't enabled in environments where we can't
            # guarantee certain behavior. Filter those out.
            if cache.get("skip-untrusted") and skip_untrusted:
                continue

            name = "level-{level}-{name}-{suffix}".format(
                level=config.params["level"],
                name=cache["name"],
                suffix=suffix,
            )
            caches[name] = cache["mount-point"]

        payload["cache"] = caches

    if features:
        payload["features"] = features
    if capabilities:
        payload["capabilities"] = capabilities


@payload_builder(
    "always-optimized",
    schema={
        Extra: object,
    },
)
@payload_builder("succeed", schema={})
def build_dummy_payload(config, job, job_def):
    job_def["payload"] = {}


transforms = TransformSequence()


@transforms.add
def set_defaults(config, jobs):
    for job in jobs:
        job.setdefault("always-target", False)
        job.setdefault("optimization", None)

        runner = job["runner"]
        if runner["implementation"] in ("kubernetes",):
            runner.setdefault("chain-of-trust", False)
            runner.setdefault("docker-in-docker", False)
            runner.setdefault("env", {})
            if "caches" in runner:
                for c in runner["caches"]:
                    c.setdefault("skip-untrusted", False)

        yield job


@transforms.add
def job_name_from_label(config, jobs):
    for job in jobs:
        if "label" not in job:
            if "name" not in job:
                raise Exception("job has neither a name nor a label")
            job["label"] = "{}-{}".format(config.kind, job["name"])
        if job.get("name"):
            del job["name"]
        yield job


@transforms.add
def validate(config, jobs):
    for job in jobs:
        validate_schema(
            job_description_schema,
            job,
            "In job {!r}:".format(job.get("label", "?no-label?")),
        )
        validate_schema(
            payload_builders[job["runner"]["implementation"]].schema,
            job["runner"],
            "In job.run {!r}:".format(job.get("label", "?no-label?")),
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

        job_def = {
            "retry": {
                "max": 2,
                "when": [
                    "unknown_failure",
                    "stale_schedule",
                    "runner_system_failure",
                    "stuck_or_timeout_failure",
                ],
            },
            "tags": [runner_tag],
            "timeout": job["runner"]["max-run-time"],
        }

        # add the payload and adjust anything else as required.
        payload_builders[job["runner"]["implementation"]].builder(config, job, job_def)

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
                "job {}/{} has too many dependencies ({} > {})".format(
                    config.kind,
                    job["label"],
                    len(job["dependencies"]),
                    MAX_DEPENDENCIES,
                )
            )
        yield job
