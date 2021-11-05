# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import json
import logging
import os
import re

import jobgraph
from jobgraph.transforms.base import TransformSequence
from jobgraph.util.docker import (
    generate_context_hash,
    create_context_tar,
)
from jobgraph.util.schema import (
    Schema,
)
from jobgraph.util.gitlab import (
    extract_gitlab_instance_and_namespace_and_name,
    get_image_full_location,
)
from voluptuous import (
    Optional,
    Required,
)
from .task import task_description_schema

logger = logging.getLogger(__name__)

CONTEXTS_DIR = "docker-contexts"

DIGEST_RE = re.compile("^[0-9a-f]{64}$")

transforms = TransformSequence()

docker_image_schema = Schema(
    {
        # Name of the docker image.
        Required("name"): str,
        # Name of the parent docker image.
        Optional("parent"): str,
        # relative path (from config.path) to the file the docker image was defined
        # in.
        Optional("job-from"): str,
        # Arguments to use for the Dockerfile.
        Optional("args"): {str: str},
        Required("container-registry-type"): str,
        # Name of the docker image definition under gitlab-ci/docker, when
        # different from the docker image name.
        Optional("definition"): str,
        # List of package tasks this docker image depends on.
        Optional("packages"): [str],
        Optional(
            "cache",
            description="Whether this image should be cached based on inputs.",
        ): bool,
    }
)


transforms.add_validate(docker_image_schema)


@transforms.add
def add_registry_specific_config(config, tasks):
    for task in tasks:
        registry_type = task.pop("container-registry-type")
        # TODO Use decorators instead
        if registry_type == "gitlab":
            worker = task.setdefault("worker", {})
            env = worker.setdefault("env", {})

            # See https://docs.gitlab.com/ee/ci/docker/using_docker_build.html#docker-in-docker-with-tls-enabled-in-kubernetes
            env["DOCKER_HOST"] = "tcp://docker:2376"
            env["DOCKER_TLS_CERTDIR"] = "/certs"
            env["DOCKER_TLS_VERIFY"] = "1"
            env["DOCKER_CERT_PATH"] = "$DOCKER_TLS_CERTDIR/client"

            worker["command"] = 'docker login --username "$CI_REGISTRY_USER" --password "$CI_REGISTRY_PASSWORD" "$CI_REGISTRY"'
            task.setdefault("optimization", {}).setdefault("skip-if-on-gitlab-container-registry", True)
        else:
            raise ValueError(f"Unknown container-registry-type: {registry_type}")

        yield task


@transforms.add
def fill_template(config, tasks):
    available_packages = set()
    for task in config.kind_dependencies_tasks:
        if task.kind != "packages":
            continue
        name = task.label.replace("packages-", "")
        available_packages.add(name)

    tasks = list(tasks)

    for task in tasks:
        image_name = task["name"]
        packages = task.get("packages", [])
        parent = task.pop("parent", None)

        for p in packages:
            if p not in available_packages:
                raise Exception(
                    "Missing package job for {}-{}: {}".format(
                        config.kind, image_name, p
                    )
                )

        description = "Build the docker image {} for use by dependent tasks".format(
            image_name
        )

        dind_image = config.graph_config["jobgraph"]["docker-in-docker-image"]

        worker = task.setdefault("worker", {})
        worker |= {
            "implementation": "kubernetes",
            "os": "linux",
            "docker-image": dind_image,
            "docker-in-docker": True,
            "max-run-time": 7200,
        }
        worker["env"] |= {
            # We use hashes as tags to reduce potential collisions of regular tags
            "DOCKER_IMAGE_NAME": image_name,
        }

        # include some information that is useful in reconstructing this task
        # from JSON
        taskdesc = {
            "label": f"build-docker-image-{image_name}",
            "description": description,
            "attributes": {
                "artifact_prefix": "public",
                "image_name": image_name,
            },
            "name": image_name,
            "optimization": task.get("optimization", None),
            "worker-type": "images",
            "worker": worker,
        }

        if packages:
            deps = taskdesc.setdefault("dependencies", {})
            for p in sorted(packages):
                deps[p] = f"packages-{p}"

        if parent:
            deps = taskdesc.setdefault("dependencies", {})
            deps["parent"] = f"build-docker-image-{parent}"
            worker["env"]["DOCKER_IMAGE_PARENT"] = {"docker-image-reference": "<parent>"}
            args = taskdesc.setdefault("args", {})
            args |= {"DOCKER_IMAGE_PARENT": "$DOCKER_IMAGE_PARENT"}

        yield taskdesc


@transforms.add
def define_docker_commands(config, tasks):
    for task in tasks:
        packages = task.pop("packages", [])
        arguments = task.get("args", {})
        worker = task.setdefault("worker", {})

        if packages:
            arguments["DOCKER_IMAGE_PACKAGES"] = " ".join(f"<{p}>" for p in packages)

        image_name = task.pop("name")
        definition = task.get("definition", image_name)
        docker_file = os.path.join("gitlab-ci", "docker", definition, "Dockerfile")
        build_args = " ".join(f'--build-arg "{argument_name}={argument_value}"' for argument_name, argument_value in arguments.items())
        worker["command"] = " && ".join((
            worker.get("command", ""),
            f'docker build --tag "$DOCKER_IMAGE_FULL_LOCATION" --file "$CI_PROJECT_DIR/{docker_file}" {build_args} .',
            'docker push "$DOCKER_IMAGE_FULL_LOCATION"',
        ))

        yield task


@transforms.add
def fill_context_hash(config, tasks):
    for task in tasks:
        image_name = task["attributes"]["image_name"]
        definition = task.pop("definition", image_name)
        args = task.pop("args", {})

        if not jobgraph.fast:
            context_path = os.path.join("gitlab-ci", "docker", definition)
            topsrcdir = os.path.dirname(config.graph_config.taskcluster_yml)
            context_hash = generate_context_hash(topsrcdir, context_path, args)
        else:
            if config.write_artifacts:
                raise Exception("Can't write artifacts if `jobgraph.fast` is set.")
            context_hash = "0" * 40

        worker = task.setdefault("worker", {})
        gitlab_domain_name, repo_namespace, repo_name = extract_gitlab_instance_and_namespace_and_name(config.params["head_repository"])
        task["attributes"] |= {
            "context_hash": context_hash,
            "docker_image_full_location": get_image_full_location(gitlab_domain_name, repo_namespace, repo_name, image_name, image_tag=context_hash, resolve_digest=True),
        }
        worker["env"] |= {
            # We use hashes as tags to reduce potential collisions of regular tags
            "DOCKER_IMAGE_TAG": context_hash,
            # We shouldn't resolve digest if we build and push image in this job
            "DOCKER_IMAGE_FULL_LOCATION": get_image_full_location(gitlab_domain_name, repo_namespace, repo_name, image_name, image_tag=context_hash, resolve_digest=False),
        }

        yield task
