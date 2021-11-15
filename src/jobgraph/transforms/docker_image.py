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
    Schema,
    docker_image_ref_or_string,
    optionally_keyed_by,
    resolve_keyed_by,
)

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
        Optional("image-name-template"): optionally_keyed_by(
            "head-ref-protection", str
        ),
        # relative path (from config.path) to the file the docker image was defined
        # in.
        Optional("job-from"): str,
        # Arguments to use for the Dockerfile.
        Optional("args"): {str: str},
        Required("container-registry-type"): str,
        # Name of the docker image definition under gitlab-ci/docker, when
        # different from the docker image name.
        Optional("definition"): str,
        # List of package jobs this docker image depends on.
        Optional("packages"): [str],
        Optional("services"): [docker_image_ref_or_string],
        Optional("variables"): dict,
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
        registry_type = job.pop("container-registry-type")
        # TODO Use decorators instead
        if registry_type == "gitlab":
            job["before_script"] = [
                'docker login --username "$CI_REGISTRY_USER" --password '
                '"$CI_REGISTRY_PASSWORD" "$CI_REGISTRY"'
            ]
            job.setdefault("optimization", {}).setdefault(
                "skip-if-on-gitlab-container-registry", True
            )
        else:
            raise ValueError(f"Unknown container-registry-type: {registry_type}")

        yield job


@transforms.add
def define_image_name(config, jobs):
    for job in jobs:
        job_name = job["name"]
        resolve_keyed_by(
            job,
            "image-name-template",
            item_name=job_name,
            **{
                "head-ref-protection": config.params["head_ref_protection"],
            },
        )
        image_name_template = job.pop("image-name-template", job_name)
        image_name = image_name_template.format(job_name=job_name)

        attributes = job.setdefault("attributes", {})
        attributes["image_name"] = image_name

        yield job


@transforms.add
def fill_template(config, jobs):
    available_packages = set()
    for job in config.stage_dependencies_tasks:
        if job.stage != "packages":
            continue
        name = job.label.replace("packages-", "")
        available_packages.add(name)

    for job in jobs:
        image_base_name = job["name"]
        packages = job.get("packages", [])

        for p in packages:
            if p not in available_packages:
                raise Exception(
                    f"Missing package job for {config.stage}-{image_base_name}: {p}"
                )

        description = (
            f"Build the docker image {image_base_name} for use by dependent jobs"
        )

        variables = job.setdefault("variables", {})
        variables |= {
            # We use hashes as tags to reduce potential collisions of regular tags
            "DOCKER_IMAGE_NAME": job["attributes"]["image_name"],
        }

        # include some information that is useful in reconstructing this job
        # from JSON
        jobdesc = {
            "label": f"build-docker-image-{image_base_name}",
            "description": description,
            "attributes": job["attributes"],
            "image": {"docker-image-reference": "<docker-in-docker>"},
            "name": image_base_name,
            "optimization": job.get("optimization", None),
            "parent": job.get("parent", None),
            "runner-alias": "images",
            "before_script": job.get("before_script", []),
            "script": job.get("script", []),
            "services": job.get("services", []),
            "variables": variables,
        }

        if packages:
            deps = jobdesc.setdefault("dependencies", {})
            for p in sorted(packages):
                deps[p] = f"packages-{p}"

        yield jobdesc


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
            parent_label = f"build-docker-image-{parent}"
            deps = job.setdefault("dependencies", {})
            deps["parent"] = parent_label
            variables["DOCKER_IMAGE_PARENT"] = {"docker-image-reference": "<parent>"}
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
            dind_image = config.graph_config["docker"]["external-images"][
                "docker-in-docker"
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
        packages = job.pop("packages", [])
        arguments = job.pop("args", {})

        if packages:
            arguments["DOCKER_IMAGE_PACKAGES"] = " ".join(f"<{p}>" for p in packages)

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
