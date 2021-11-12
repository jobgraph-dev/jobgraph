# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import logging
import os
import sys

import attr
import yaml
from voluptuous import Extra, Optional, Required

from .errors import MissingImageDigest
from .util import path
from .util.docker_registries import does_image_full_location_have_digest
from .util.python_path import find_object
from .util.schema import Schema, optionally_keyed_by, validate_schema
from .util.yaml import load_yaml

logger = logging.getLogger(__name__)

DEFAULT_ROOT_DIR = os.path.join("gitlab-ci", "ci")

graph_config_schema = Schema(
    {
        Required("runners"): {
            Required("aliases"): {
                str: {
                    Required("implementation"): str,
                    Required("os"): str,
                    Required("runner-tag"): optionally_keyed_by("level", str),
                }
            },
        },
        Required("jobgraph"): {
            Optional(
                "register",
                description="Python function to call to register extensions.",
            ): str,
            Optional("decision-parameters"): str,
            Required("external-docker-images"): {str: str},
            # TODO enforce stricter dictionaries
            Required("container-registry"): dict,
        },
        # TODO enforce stricter dictionaries
        Required("job-defaults"): dict,
        Extra: object,
    }
)


@attr.s(frozen=True, cmp=False)
class GraphConfig:
    _config = attr.ib()
    root_dir = attr.ib()

    _PATH_MODIFIED = False

    def __getitem__(self, name):
        return self._config[name]

    def __contains__(self, name):
        return name in self._config

    def register(self):
        """
        Add the project's jobgraph directory to the python path, and register
        any extensions present.
        """
        modify_path = os.path.dirname(self.root_dir)
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
        if path.split(self.root_dir)[-2:] != path.split(DEFAULT_ROOT_DIR):
            raise Exception(
                "Not guessing path to vcs root. "
                "Graph config in non-standard location."
            )
        return os.path.dirname(os.path.dirname(self.root_dir))

    @property
    def gitlab_ci_yml(self):
        if path.split(self.root_dir)[-2:] != path.split(DEFAULT_ROOT_DIR):
            raise Exception(
                "Not guessing path to `.gitlab-ci.yml`. "
                "Graph config in non-standard location."
            )
        return os.path.join(
            os.path.dirname(os.path.dirname(self.root_dir)),
            ".gitlab-ci.yml",
        )

    @property
    def config_yml(self):
        if path.split(self.root_dir)[-2:] != path.split(DEFAULT_ROOT_DIR):
            raise Exception(
                "Not guessing path to `config.yml`. "
                "Graph config in non-standard location."
            )
        return os.path.join(
            self.root_dir,
            "config.yml",
        )

    def write(self):
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

    for external_image in config["jobgraph"].get("external-docker-images", {}).values():
        if not does_image_full_location_have_digest(external_image):
            raise MissingImageDigest(external_image, config_yml)


def load_graph_config(root_dir):
    config_yml = os.path.join(root_dir, "config.yml")
    if not os.path.exists(config_yml):
        raise Exception(f"Couldn't find jobgraph configuration: {config_yml}")

    logger.debug(f"loading config from `{config_yml}`")
    config = load_yaml(config_yml)

    validate_graph_config(config, config_yml)
    return GraphConfig(config=config, root_dir=root_dir)
