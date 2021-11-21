# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import logging
import os
import re

from dockerfile_parse import DockerfileParser
from voluptuous import Optional, Required

import jobgraph
from jobgraph.errors import MissingImageDigest
from jobgraph.transforms.base import TransformSequence
from jobgraph.util.docker import generate_context_hash
from jobgraph.util.docker_registries import does_image_full_location_have_digest
from jobgraph.util.docker_registries.gitlab import get_image_full_location
from jobgraph.util.gitlab import extract_gitlab_instance_and_namespace_and_name
from jobgraph.util.schema import (
    docker_image_ref,
    gitlab_ci_job_input,
    optionally_keyed_by,
    resolve_keyed_by,
)

logger = logging.getLogger(__name__)

CONTEXTS_DIR = "docker-contexts"

DIGEST_RE = re.compile("^[0-9a-f]{64}$")

transforms = TransformSequence()

docker_image_schema = gitlab_ci_job_input.extend(
    {
        # Arguments to use for the Dockerfile.
        Optional("args"): {str: str},
        Required("container_registry_type"): str,
        # Name of the docker image definition under gitlab-ci/docker, when
        # different from the docker image name.
        Optional("definition"): str,
        Optional("description"): str,
        Optional("image"): docker_image_ref,
        Optional("image_name_template"): optionally_keyed_by(
            "head_ref_protection", str
        ),
        # relative path (from config.path) to the file the docker image was defined
        # in.
        Optional("job_from"): str,
        Optional("label"): str,
        Required("name"): str,
        # Name of the parent docker image.
        Optional("parent"): str,
        Optional("push_as_latest"): optionally_keyed_by("head_ref", bool),
    }
)


transforms.add_validate(docker_image_schema)


@transforms.add
def ensure_external_base_images_have_digests(config, jobs):
    for job in jobs:
        image_name = job["name"]
        definition = job.get("definition", image_name)
        docker_file_path = os.path.join("gitlab-ci", "docker", definition, "Dockerfile")
        docker_file = DockerfileParser(docker_file_path)

        # baseimage is not defined if it's built within jobgraph
        if docker_file.baseimage and not does_image_full_location_have_digest(
            docker_file.baseimage
        ):
            raise MissingImageDigest("base docker image", docker_file_path)

        yield job


@transforms.add
def add_registry_specific_config(config, jobs):
    for job in jobs:
        registry_type = job.pop("container_registry_type")
        # TODO Use decorators instead
        if registry_type == "gitlab":
            job["before_script"] = [
                'docker login --username "$CI_REGISTRY_USER" --password '
                '"$CI_REGISTRY_PASSWORD" "$CI_REGISTRY"'
            ]
            job.setdefault("optimization", {}).setdefault(
                "skip_if_on_gitlab_container_registry", True
            )
        else:
            raise ValueError(f"Unknown container_registry_type: {registry_type}")

        yield job


@transforms.add
def resolve_keyed_variables(config, jobs):
    for job in jobs:
        for key in ("image_name_template", "push_as_latest"):
            resolve_keyed_by(
                job,
                key,
                item_name=job["name"],
                **{
                    "head_ref_protection": config.params["head_ref_protection"],
                    "head_ref": config.params["head_ref"],
                },
            )

        yield job


@transforms.add
def define_image_name(config, jobs):
    for job in jobs:
        job_name = job["name"]
        image_name_template = job.pop("image_name_template", job_name)
        image_name = image_name_template.format(job_name=job_name)

        attributes = job.setdefault("attributes", {})
        attributes["image_name"] = image_name

        variables = job.setdefault("variables", {})
        variables |= {
            # We use hashes as tags to reduce potential collisions of regular tags
            "DOCKER_IMAGE_NAME": image_name,
        }

        yield job


@transforms.add
def fill_common_values(config, jobs):
    for job in jobs:
        image_base_name = job["name"]

        job |= {
            "label": image_base_name,
            "description": f"Build the docker image {image_base_name} for use by downstream jobs",
            "image": {"docker_image_reference": "<docker_in_docker>"},
            "runner_alias": "images",
        }

        yield job


@transforms.add
def fill_context_hash(config, jobs):
    jobs_list = list(jobs)

    for job in jobs_list:
        image_base_name = job["name"]
        definition = job.pop("definition", image_base_name)
        parent = job.pop("parent", None)
        args = job.setdefault("args", {})
        variables = job.setdefault("variables", {})

        if parent:
            parent_label = parent
            deps = job.setdefault("dependencies", {})
            deps["parent"] = parent_label
            variables["DOCKER_IMAGE_PARENT"] = {"docker_image_reference": "<parent>"}
            # If 2 parent jobs have the same name, then JobGraph will complain later
            parent_job = [j for j in jobs_list if j["label"] == parent_label][0]

            args |= {
                "DOCKER_IMAGE_PARENT": parent_job["attributes"][
                    "docker_image_full_location"
                ]
            }

        if not jobgraph.fast:
            context_path = os.path.join("gitlab-ci", "docker", definition)
            topsrcdir = os.path.dirname(config.graph_config.gitlab_ci_yml)
            # We need to use the real full location (not a reference to) here because
            # the context hash depends on it.
            dind_image = config.graph_config["docker"]["external_images"][
                "docker_in_docker"
            ]
            context_hash = generate_context_hash(
                topsrcdir, context_path, args, dind_image_full_location=dind_image
            )
        else:
            if config.write_artifacts:
                raise Exception("Can't write artifacts if `jobgraph.fast` is set.")
            context_hash = "0" * 40

        (
            gitlab_domain_name,
            repo_namespace,
            repo_name,
        ) = extract_gitlab_instance_and_namespace_and_name(
            config.params["head_repository"]
        )

        docker_image_full_location = get_image_full_location(
            gitlab_domain_name,
            repo_namespace,
            repo_name,
            job["attributes"]["image_name"],
            image_tag=context_hash,
        )
        job["attributes"] |= {
            "context_hash": context_hash,
            "docker_image_full_location": docker_image_full_location,
        }
        variables |= {
            # We use hashes as tags to reduce potential collisions of regular tags
            "DOCKER_IMAGE_TAG": context_hash,
            # We shouldn't resolve digest if we build and push image in this job
            "DOCKER_IMAGE_FULL_LOCATION": docker_image_full_location,
        }

        yield job


@transforms.add
def define_docker_script_instructions(config, jobs):
    for job in jobs:
        arguments = job.pop("args", {})

        image_name = job.pop("name")
        definition = job.get("definition", image_name)
        docker_file = os.path.join("gitlab-ci", "docker", definition, "Dockerfile")
        build_args = " ".join(
            f'--build-arg "{argument_name}={argument_value}"'
            for argument_name, argument_value in arguments.items()
        )
        script = job.setdefault("script", [])
        script.extend(
            [
                'docker build --tag "$DOCKER_IMAGE_FULL_LOCATION" --file '
                f'"$CI_PROJECT_DIR/{docker_file}" {build_args} .',
                'docker push "$DOCKER_IMAGE_FULL_LOCATION"',
            ]
        )

        yield job


@transforms.add
def define_whether_image_should_be_pushed_as_latest(config, jobs):
    for job in jobs:
        push_as_latest = job.pop("push_as_latest", False)
        if push_as_latest:
            docker_image_latest_location = get_image_full_location(
                *extract_gitlab_instance_and_namespace_and_name(
                    config.params["head_repository"]
                ),
                image_name=job["attributes"]["image_name"],
                image_tag="latest",
            )
            variables = job.setdefault("variables", {})
            variables |= {
                "DOCKER_IMAGE_LATEST_LOCATION": docker_image_latest_location,
            }

            script = job.setdefault("script", [])
            script.extend(
                [
                    'docker tag "$DOCKER_IMAGE_FULL_LOCATION" "$DOCKER_IMAGE_LATEST_LOCATION"',
                    'docker push "$DOCKER_IMAGE_LATEST_LOCATION"',
                ]
            )

        yield job
