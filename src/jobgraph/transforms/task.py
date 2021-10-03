# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
These transformations take a task description and turn it into a TaskCluster
task definition (along with attributes, label, etc.).  The input to these
transformations is generic to any kind of task, but abstracts away some of the
complexities of worker implementations.
"""


import hashlib
import os
import re
import time
from copy import deepcopy

import attr

from jobgraph.util.hash import hash_path
from jobgraph.util.keyed_by import evaluate_keyed_by
from jobgraph.util.memoize import memoize
from jobgraph.transforms.base import TransformSequence
from jobgraph.util.schema import (
    validate_schema,
    Schema,
    optionally_keyed_by,
    resolve_keyed_by,
    OptimizationSchema,
    taskref_or_string,
)
from jobgraph.util.workertypes import worker_type_implementation
from voluptuous import Any, Required, Optional, Extra, All, NotIn
from jobgraph import MAX_DEPENDENCIES
from ..util import docker as dockerutil
from ..util.workertypes import get_worker_type

RUN_TASK = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "run-task", "run-task"
)


@memoize
def _run_task_suffix():
    """String to append to cache names under control of run-task."""
    return hash_path(RUN_TASK)[0:20]


# A task description is a general description of a TaskCluster task
task_description_schema = Schema(
    {
        # the label for this task
        Required("label"): str,
        # description of the task (for metadata)
        Required("description"): str,
        # attributes for this task
        Optional("attributes"): {str: object},
        # relative path (from config.path) to the file task was defined in
        Optional("job-from"): str,
        # dependencies of this task, keyed by name; these are passed through
        # verbatim and subject to the interpretation of the Task's get_dependencies
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
        # Soft dependencies of this task, as a list of tasks labels
        Optional("soft-dependencies"): [str],
        # custom "task.extra" content
        Optional("extra"): {str: object},
        # information for indexing this build so its artifacts can be discovered;
        # if omitted, the build will not be indexed.
        Optional("index"): {
            # the name of the product this build produces
            "product": str,
            # the names to use for this job in the TaskCluster index
            "job-name": str,
            # Type of gecko v2 index to use
            "type": str,
            # The rank that the task will receive in the TaskCluster
            # index.  A newly completed task supercedes the currently
            # indexed task iff it has a higher rank.  If unspecified,
            # 'by-tier' behavior will be used.
            "rank": Any(
                # Rank is equal the timestamp of the build_date for tier-1
                # tasks, and zero for non-tier-1.  This sorts tier-{2,3}
                # builds below tier-1 in the index.
                "by-tier",
                # Rank is given as an integer constant (e.g. zero to make
                # sure a task is last in the index).
                int,
                # Rank is equal to the timestamp of the build_date.  This
                # option can be used to override the 'by-tier' behavior
                # for non-tier-1 tasks.
                "build_date",
            ),
        },
        Optional("run-on-pipeline-sources"): [str],
        Optional("run-on-git-branches"): [str],
        # The `always-target` attribute will cause the task to be included in the
        # target_task_graph regardless of filtering. Tasks included in this manner
        # will be candidates for optimization even when `optimize_target_tasks` is
        # False, unless the task was also explicitly chosen by the target_tasks
        # method.
        Required("always-target"): bool,
        # Optimization to perform on this task during the optimization phase.
        # Optimizations are defined in taskcluster/taskgraph/optimize.py.
        Required("optimization"): OptimizationSchema,
        # the provisioner-id/worker-type for the task.  The following parameters will
        # be substituted in this string:
        #  {level} -- the scm level of this push
        "worker-type": str,
        # Whether the job should use sccache compiler caching.
        Required("needs-sccache"): bool,
        # information specific to the worker implementation that will run this task
        Optional("worker"): {
            Required("implementation"): str,
            Extra: object,
        },
    }
)


def get_branch_rev(config):
    return config.params["head_rev"]


@memoize
def get_default_priority(graph_config, project):
    return evaluate_keyed_by(
        graph_config["task-priority"], "Graph Config", {"project": project}
    )


# define a collection of payload builders, depending on the worker implementation
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


# define a collection of index builders, depending on the type implementation
index_builders = {}


def index_builder(name):
    def wrap(func):
        index_builders[name] = func
        return func

    return wrap


UNSUPPORTED_INDEX_PRODUCT_ERROR = """\
The index product {product} is not in the list of configured products in
`taskcluster/ci/config.yml'.
"""


def verify_index(config, index):
    product = index["product"]
    if product not in config.graph_config["index"]["products"]:
        raise Exception(UNSUPPORTED_INDEX_PRODUCT_ERROR.format(product=product))


@payload_builder(
    "docker-worker",
    schema={
        Required("os"): "linux",
        # For tasks that will run in docker-worker, this is the name of the docker
        # image or in-tree docker image to run the task in.  If in-tree, then a
        # dependency will be created automatically.  This is generally
        # `desktop-test`, or an image that acts an awful lot like it.
        Required("docker-image"): Any(
            # a raw Docker image path (repo/image:tag)
            str,
            # an in-tree generated docker image (from `gitlab-ci/docker/<name>`)
            {"in-tree": str},
            # an indexed docker image
            {"indexed": str},
        ),
        # worker features that should be enabled
        Required("relengapi-proxy"): bool,
        Required("chain-of-trust"): bool,
        Required("taskcluster-proxy"): bool,
        Required("allow-ptrace"): bool,
        Required("loopback-video"): bool,
        Required("loopback-audio"): bool,
        Required("docker-in-docker"): bool,  # (aka 'dind')
        Required("privileged"): bool,
        # Paths to Docker volumes.
        #
        # For in-tree Docker images, volumes can be parsed from Dockerfile.
        # This only works for the Dockerfile itself: if a volume is defined in
        # a base image, it will need to be declared here. Out-of-tree Docker
        # images will also require explicit volume annotation.
        #
        # Caches are often mounted to the same path as Docker volumes. In this
        # case, they take precedence over a Docker volume. But a volume still
        # needs to be declared for the path.
        Optional("volumes"): [str],
        # caches to set up for the task
        Optional("caches"): [
            {
                # only one type is supported by any of the workers right now
                "type": "persistent",
                # name of the cache, allowing re-use by subsequent tasks naming the
                # same cache
                "name": str,
                # location in the task image where the cache will be mounted
                "mount-point": str,
                # Whether the cache is not used in untrusted environments
                # (like the Try repo).
                Optional("skip-untrusted"): bool,
            }
        ],
        # artifacts to extract from the task image after completion
        Optional("artifacts"): [
            {
                # type of artifact -- simple file, or recursive directory
                "type": Any("file", "directory"),
                # task image path from which to read artifact
                "path": str,
                # name of the produced artifact (root of the names for
                # type=directory)
                "name": str,
            }
        ],
        # environment variables
        Required("env"): {str: taskref_or_string},
        # the command to run; if not given, docker-worker will default to the
        # command in the docker image
        Optional("command"): [taskref_or_string],
        # the maximum time to run, in seconds
        Required("max-run-time"): int,
        # the exit status code(s) that indicates the task should be retried
        Optional("retry-exit-status"): [int],
        # the exit status code(s) that indicates the caches used by the task
        # should be purged
        Optional("purge-caches-exit-status"): [int],
        # Wether any artifacts are assigned to this worker
        Optional("skip-artifacts"): bool,
    },
)
def build_docker_worker_payload(config, task, task_def):
    worker = task["worker"]
    level = int(config.params["level"])

    image = worker["docker-image"]
    if isinstance(image, dict):
        if "in-tree" in image:
            name = image["in-tree"]
            docker_image_task = "build-docker-image-" + image["in-tree"]
            task.setdefault("dependencies", {})["docker-image"] = docker_image_task

            image = {
                "path": "public/image.tar.zst",
                "taskId": {"task-reference": "<docker-image>"},
                "type": "task-image",
            }

            # Find VOLUME in Dockerfile.
            volumes = dockerutil.parse_volumes(name)
            for v in sorted(volumes):
                if v in worker["volumes"]:
                    raise Exception(
                        "volume %s already defined; "
                        "if it is defined in a Dockerfile, "
                        "it does not need to be specified in the "
                        "worker definition" % v
                    )

                worker["volumes"].append(v)

        elif "indexed" in image:
            image = {
                "path": "public/image.tar.zst",
                "namespace": image["indexed"],
                "type": "indexed-image",
            }
        else:
            raise Exception("unknown docker image type")

    features = {}

    if worker.get("docker-in-docker"):
        features["dind"] = True

    capabilities = {}

    task_def["image"] = image
    task_def["variables"] = worker["env"]

    if "command" in worker:
        task_def["script"] = worker["command"]

    if "max-run-time" in worker:
        task_def["timeout"] = f'{worker["max-run-time"]} seconds'

    payload = {}
    run_task = payload.get("command", [""])[0].endswith("run-task")

    if "artifacts" in worker:
        task_def["artifacts"] = {
            "expire_in": "3 months",    # TODO: Parametrize
            "paths": [
                artifact["path"]
                for artifact in worker["artifacts"]
            ],
            "public": False,    # TODO: Parametrize
            "reports": {},  # TODO: Support different types of reports
        }

    if isinstance(worker.get("docker-image"), str):
        out_of_tree_image = worker["docker-image"]
    else:
        out_of_tree_image = None
        image = worker.get("docker-image", {}).get("in-tree")

    if "caches" in worker:
        caches = {}

        # run-task knows how to validate caches.
        #
        # To help ensure new run-task features and bug fixes don't interfere
        # with existing caches, we seed the hash of run-task into cache names.
        # So, any time run-task changes, we should get a fresh set of caches.
        # This means run-task can make changes to cache interaction at any time
        # without regards for backwards or future compatibility.
        #
        # But this mechanism only works for in-tree Docker images that are built
        # with the current run-task! For out-of-tree Docker images, we have no
        # way of knowing their content of run-task. So, in addition to varying
        # cache names by the contents of run-task, we also take the Docker image
        # name into consideration. This means that different Docker images will
        # never share the same cache. This is a bit unfortunate. But it is the
        # safest thing to do. Fortunately, most images are defined in-tree.
        #
        # For out-of-tree Docker images, we don't strictly need to incorporate
        # the run-task content into the cache name. However, doing so preserves
        # the mechanism whereby changing run-task results in new caches
        # everywhere.

        # As an additional mechanism to force the use of different caches, the
        # string literal in the variable below can be changed. This is
        # preferred to changing run-task because it doesn't require images
        # to be rebuilt.
        cache_version = "v3"

        if run_task:
            suffix = f"{cache_version}-{_run_task_suffix()}"

            if out_of_tree_image:
                name_hash = hashlib.sha256(out_of_tree_image).hexdigest()
                suffix += name_hash[0:12]

        else:
            suffix = cache_version

        skip_untrusted = config.params.is_try() or level == 1

        for cache in worker["caches"]:
            # Some caches aren't enabled in environments where we can't
            # guarantee certain behavior. Filter those out.
            if cache.get("skip-untrusted") and skip_untrusted:
                continue

            name = "{trust_domain}-level-{level}-{name}-{suffix}".format(
                trust_domain=config.graph_config["trust-domain"],
                level=config.params["level"],
                name=cache["name"],
                suffix=suffix,
            )
            caches[name] = cache["mount-point"]

        # Assertion: only run-task is interested in this.
        if run_task:
            payload["env"]["TASKCLUSTER_CACHES"] = ";".join(sorted(caches.values()))

        payload["cache"] = caches

    # And send down volumes information to run-task as well.
    if run_task and worker.get("volumes"):
        payload["env"]["TASKCLUSTER_VOLUMES"] = ";".join(sorted(worker["volumes"]))

    if features:
        payload["features"] = features
    if capabilities:
        payload["capabilities"] = capabilities

    check_caches_are_volumes(task)


@payload_builder(
    "always-optimized",
    schema={
        Extra: object,
    },
)
@payload_builder("succeed", schema={})
def build_dummy_payload(config, task, task_def):
    task_def["payload"] = {}


transforms = TransformSequence()


@transforms.add
def set_defaults(config, tasks):
    for task in tasks:
        task.setdefault("always-target", False)
        task.setdefault("optimization", None)
        task.setdefault("needs-sccache", False)

        worker = task["worker"]
        if worker["implementation"] in ("docker-worker",):
            worker.setdefault("relengapi-proxy", False)
            worker.setdefault("chain-of-trust", False)
            worker.setdefault("taskcluster-proxy", False)
            worker.setdefault("allow-ptrace", False)
            worker.setdefault("loopback-video", False)
            worker.setdefault("loopback-audio", False)
            worker.setdefault("docker-in-docker", False)
            worker.setdefault("privileged", False)
            worker.setdefault("volumes", [])
            worker.setdefault("env", {})
            if "caches" in worker:
                for c in worker["caches"]:
                    c.setdefault("skip-untrusted", False)

        yield task


@transforms.add
def task_name_from_label(config, tasks):
    for task in tasks:
        if "label" not in task:
            if "name" not in task:
                raise Exception("task has neither a name nor a label")
            task["label"] = "{}-{}".format(config.kind, task["name"])
        if task.get("name"):
            del task["name"]
        yield task


@transforms.add
def validate(config, tasks):
    for task in tasks:
        validate_schema(
            task_description_schema,
            task,
            "In task {!r}:".format(task.get("label", "?no-label?")),
        )
        validate_schema(
            payload_builders[task["worker"]["implementation"]].schema,
            task["worker"],
            "In task.run {!r}:".format(task.get("label", "?no-label?")),
        )
        yield task


@transforms.add
def build_task(config, tasks):
    for task in tasks:
        level = str(config.params["level"])

        provisioner_id, worker_type = get_worker_type(
            config.graph_config,
            task["worker-type"],
            level,
        )
        task["worker-type"] = "/".join([provisioner_id, worker_type])
        project = config.params["project"]

        # set up extra
        extra = task.get("extra", {})
        extra["parent"] = os.environ.get("TASK_ID", "")

        if "priority" not in task:
            task["priority"] = get_default_priority(
                config.graph_config, config.params["project"]
            )

        task_def = {
            "image": "ubuntu:20.04",
            "retry": {
                "max": 2,
                "when": [
                    "unknown_failure",
                    "stale_schedule",
                    "runner_system_failure",
                    "stuck_or_timeout_failure",
                ],
            },
            "tags": [worker_type],
            "cache": {},
            "timeout": task["worker"]["max-run-time"],
            "needs": [],
        }

        # add the payload and adjust anything else as required.
        payload_builders[task["worker"]["implementation"]].builder(
            config, task, task_def
        )

        attributes = task.get("attributes", {})
        attributes["run_on_pipeline_sources"] = task.get("run-on-pipeline-sources", ["all"])
        attributes["run_on_git_branches"] = task.get("run-on-git-branches", ["all"])
        attributes["always_target"] = task["always-target"]

        yield {
            "label": task["label"],
            "description": task["description"],
            "task": task_def,
            "dependencies": task.get("dependencies", {}),
            "soft-dependencies": task.get("soft-dependencies", []),
            "attributes": attributes,
            "optimization": task.get("optimization", None),
        }


@transforms.add
def check_task_dependencies(config, tasks):
    """Ensures that tasks don't have more than 100 dependencies."""
    for task in tasks:
        if len(task["dependencies"]) > MAX_DEPENDENCIES:
            raise Exception(
                "task {}/{} has too many dependencies ({} > {})".format(
                    config.kind,
                    task["label"],
                    len(task["dependencies"]),
                    MAX_DEPENDENCIES,
                )
            )
        yield task


def check_caches_are_volumes(task):
    """Ensures that all cache paths are defined as volumes.

    Caches and volumes are the only filesystem locations whose content
    isn't defined by the Docker image itself. Some caches are optional
    depending on the job environment. We want paths that are potentially
    caches to have as similar behavior regardless of whether a cache is
    used. To help enforce this, we require that all paths used as caches
    to be declared as Docker volumes. This check won't catch all offenders.
    But it is better than nothing.
    """
    volumes = set(task["worker"]["volumes"])
    paths = {c["mount-point"] for c in task["worker"].get("caches", [])}
    missing = paths - volumes

    if not missing:
        return

    raise Exception(
        "task %s (image %s) has caches that are not declared as "
        "Docker volumes: %s "
        "(have you added them as VOLUMEs in the Dockerfile?)"
        % (task["label"], task["worker"]["docker-image"], ", ".join(sorted(missing)))
    )