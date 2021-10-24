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
            # TODO Use variables already defined by jobgraph
            env["DOCKER_IMAGE_FULL_TAG"] = "$CI_REGISTRY/$CI_PROJECT_NAMESPACE/$CI_PROJECT_NAME/$DOCKER_IMAGE_NAME:$DOCKER_IMAGE_TAG"

            # See https://docs.gitlab.com/ee/ci/docker/using_docker_build.html#docker-in-docker-with-tls-enabled-in-kubernetes
            env["DOCKER_HOST"] = "tcp://docker:2376"
            env["DOCKER_TLS_CERTDIR"] = "/certs"
            env["DOCKER_TLS_VERIFY"] = "1"
            env["DOCKER_CERT_PATH"] = "$DOCKER_TLS_CERTDIR/client"

            image_name = task.get("name")
            definition = task.get("definition", image_name)
            docker_file = os.path.join("gitlab-ci", "docker", definition, "Dockerfile")
            worker["command"] = " && ".join((
                'docker login --username "$CI_REGISTRY_USER" --password "$CI_REGISTRY_PASSWORD" "$CI_REGISTRY"',
                # Registry must be lowercase
                'export DOCKER_IMAGE_FULL_TAG="$(echo "$DOCKER_IMAGE_FULL_TAG" | tr \'[:upper:]\' \'[:lower:]\')"',
                f'docker build --tag "$DOCKER_IMAGE_FULL_TAG" --file "$CI_PROJECT_DIR/{docker_file}" .',
                'docker push "$DOCKER_IMAGE_FULL_TAG"',
            ))
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

    context_hashes = {}

    tasks = list(tasks)

    for task in tasks:
        image_name = task.pop("name")
        args = task.pop("args", {})
        definition = task.pop("definition", image_name)
        packages = task.pop("packages", [])
        parent = task.pop("parent", None)

        for p in packages:
            if p not in available_packages:
                raise Exception(
                    "Missing package job for {}-{}: {}".format(
                        config.kind, image_name, p
                    )
                )

        if not jobgraph.fast:
            context_path = os.path.join("gitlab-ci", "docker", definition)
            topsrcdir = os.path.dirname(config.graph_config.taskcluster_yml)
            context_hash = generate_context_hash(topsrcdir, context_path, args)
        else:
            if config.write_artifacts:
                raise Exception("Can't write artifacts if `jobgraph.fast` is set.")
            context_hash = "0" * 40
        digest_data = [context_hash]
        digest_data += [json.dumps(args, sort_keys=True)]
        context_hashes[image_name] = context_hash

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
            "DOCKER_IMAGE_TAG": context_hash,
            "DOCKER_IMAGE_NAME": image_name,
        }

        if packages:
            args["DOCKER_IMAGE_PACKAGES"] = " ".join(f"<{p}>" for p in packages)
        if args:
            worker["env"]["DOCKER_BUILD_ARGS"] = {
                "task-reference": json.dumps(args),
            }

        # include some information that is useful in reconstructing this task
        # from JSON
        taskdesc = {
            "label": f"build-docker-image-{image_name}",
            "description": description,
            "attributes": {
                "image_name": image_name,
                "artifact_prefix": "public",
            },
            "worker-type": "images",
            "worker": worker,
        }

        digest_data.append(f"docker-in-docker-image:{dind_image}")

        if packages:
            deps = taskdesc.setdefault("dependencies", {})
            for p in sorted(packages):
                deps[p] = f"packages-{p}"

        if parent:
            deps = taskdesc.setdefault("dependencies", {})
            deps["parent"] = f"build-docker-image-{parent}"
            worker["env"]["PARENT_TASK_ID"] = {
                "task-reference": "<parent>",
            }

        yield taskdesc
