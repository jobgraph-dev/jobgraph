import logging
import os
import sys

import attr
import yaml
from voluptuous import Extra, Optional, Required

from .errors import MissingImageDigest
from .paths import get_config_yml_path, get_gitlab_ci_dir
from .util.docker_registries import does_image_full_location_have_digest
from .util.python_path import find_object
from .util.schema import (
    Schema,
    docker_image_ref,
    gitlab_ci_job_input,
    optionally_keyed_by,
    validate_schema,
)
from .util.yaml import load_yaml

logger = logging.getLogger(__name__)

DEFAULT_ROOT_DIR = os.path.join("gitlab-ci", "stages")

graph_config_schema = Schema(
    {
        Optional("cache"): {
            Required("type"): str,
            Required("bucket_name"): str,
        },
        Required("docker"): {
            Required("external_images"): {
                Required("docker_in_docker"): str,
                Extra: str,
            },
        },
        Required("gitlab"): {
            Required("root_url"): str,
            Required("project_id"): int,
        },
        Required("job_defaults"): gitlab_ci_job_input.extend(
            {
                # Make all required fields optional for job_defaults
                Optional("description"): str,
                Optional("image"): docker_image_ref,
                Optional("label"): str,
            }
        ),
        Optional("jobgraph"): {
            Optional(
                "register",
                description="Python function to call to register extensions.",
            ): str,
            Optional("decision_parameters"): str,
        },
        Required("runners"): {
            Required("aliases"): {
                str: {
                    Required("runner_tag"): optionally_keyed_by(
                        "head_ref_protection", str
                    ),
                }
            },
        },
        Extra: object,
    }
)


@attr.s(frozen=True, cmp=False)
class GraphConfig:
    _config = attr.ib()
    root_dir = attr.ib()

    _PATH_MODIFIED = False

    def __attrs_post_init__(self):
        self._config.setdefault("jobgraph", {})

    def __getitem__(self, name):
        return self._config[name]

    def __contains__(self, name):
        return name in self._config

    def register(self):
        """
        Add the project's jobgraph directory to the python path, and register
        any extensions present.
        """
        modify_path = self.root_dir
        if GraphConfig._PATH_MODIFIED:
            if GraphConfig._PATH_MODIFIED == modify_path:
                # Already modified path with the same root_dir.
                # We currently need to do this to enable actions to call
                # jobgraph_decision, e.g. relpro.
                return
            raise Exception("Can't register multiple directories on python path.")
        GraphConfig._PATH_MODIFIED = modify_path
        sys.path.insert(0, modify_path)
        register_path = self["jobgraph"].get("register")
        if register_path:
            find_object(register_path)(self)

    @property
    def vcs_root(self):
        return os.path.dirname(self.root_dir)

    @property
    def gitlab_ci_yml(self):
        return os.path.join(
            os.path.dirname(self.root_dir),
            ".gitlab-ci.yml",
        )

    @property
    def config_yml(self):
        return get_config_yml_path(self.root_dir)

    def write(self):
        target_dir = os.path.dirname(self.config_yml)
        if not os.path.isdir(target_dir):
            os.makedirs(target_dir)

        with open(self.config_yml, "w") as f:
            yaml.safe_dump(
                self._config,
                f,
                allow_unicode=True,
                default_flow_style=False,
                explicit_start=True,
                indent=4,
            )


def validate_graph_config(config, config_yml):
    validate_schema(graph_config_schema, config, "Invalid graph configuration:")

    for external_image in config["docker"].get("external_images", {}).values():
        if not does_image_full_location_have_digest(external_image):
            raise MissingImageDigest(external_image, config_yml)


def load_graph_config(root_dir=get_gitlab_ci_dir(), validate_config=True):
    # TODO set root_dir to be the one containing config.yml
    config_yml = get_config_yml_path(root_dir)
    if not os.path.exists(config_yml):
        raise Exception(f"Couldn't find jobgraph configuration: {config_yml}")

    logger.debug(f"loading config from `{config_yml}`")
    config = load_yaml(config_yml)

    if validate_config:
        validate_graph_config(config, config_yml)
    return GraphConfig(config=config, root_dir=root_dir)
