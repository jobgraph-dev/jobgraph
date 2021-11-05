# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import hashlib
import json
import os
import time
from datetime import datetime
from pprint import pformat
from urllib.parse import urlparse
from urllib.request import urlopen

from jobgraph.util.memoize import memoize
from jobgraph.util.readonlydict import ReadOnlyDict
from jobgraph.util.schema import validate_schema
from jobgraph.util.vcs import get_repository
from voluptuous import (
    ALLOW_EXTRA,
    Required,
    Optional,
    Schema,
)


class ParameterMismatch(Exception):
    """Raised when a parameters.yml has extra or missing parameters."""


@memoize
def _repo():
    return get_repository(os.getcwd())


# Please keep this list sorted and in sync with taskcluster/docs/parameters.rst
base_schema = Schema(
    {
        Required("base_repository"): str,
        Required("build_date"): int,
        Required("do_not_optimize"): [str],
        Required("existing_tasks"): {str: str},
        Required("filters"): [str],
        Required("head_ref"): str,
        Required("head_repository"): str,
        Required("head_rev"): str,
        Required("head_tag"): str,
        Required("level"): str,
        Required("optimize_target_tasks"): bool,
        Required("owner"): str,
        Required("project"): str,
        Required("pushdate"): int,
        # target-kind is not included, since it should never be
        # used at run-time
        Required("target_tasks_method"): str,
        Required("pipeline_source"): str,
    }
)

GIT_REPO_PROVIDERS = ("github", "gitlab")


def extend_parameters_schema(schema):
    """
    Extend the schema for parameters to include per-project configuration.

    This should be called by the `jobgraph.register` function in the
    graph-configuration.
    """
    global base_schema
    base_schema = base_schema.extend(schema)


class Parameters(ReadOnlyDict):
    """An immutable dictionary with nicer KeyError messages on failure"""

    def __init__(self, strict=True, **kwargs):
        self.strict = strict
        self.spec = kwargs.pop("spec", None)
        self._id = None

        if not self.strict:
            # apply defaults to missing parameters
            kwargs = Parameters._fill_defaults(**kwargs)

        ReadOnlyDict.__init__(self, **kwargs)

    @property
    def id(self):
        if not self._id:
            self._id = hashlib.sha256(
                json.dumps(self, sort_keys=True).encode("utf-8")
            ).hexdigest()[:12]

        return self._id

    @staticmethod
    def format_spec(spec):
        """
        Get a friendly identifier from a parameters specifier.

        Args:
            spec (str): Parameters specifier.

        Returns:
            str: Name to identify parameters by.
        """
        if spec is None:
            return "defaults"

        if any(spec.startswith(s) for s in ("task-id=", "project=")):
            return spec

        result = urlparse(spec)
        if result.scheme in ("http", "https"):
            spec = result.path

        return os.path.splitext(os.path.basename(spec))[0]

    @staticmethod
    def _fill_defaults(**kwargs):
        defaults = {
            "base_repository": _repo().get_url(),
            "build_date": int(time.time()),
            "do_not_optimize": [],
            "existing_tasks": {},
            "filters": ["target_tasks_method"],
            "head_ref": _repo().head_ref,
            "head_repository": _repo().get_url(),
            "head_rev": _repo().head_ref,
            "head_tag": "",
            "level": "3",
            "optimize_target_tasks": True,
            "owner": "nobody@mozilla.com",
            "project": _repo().get_url().rsplit("/", 1)[1],
            "pushdate": int(time.time()),
            "target_tasks_method": "default",
            "pipeline_source": "",
        }

        for name, default in defaults.items():
            if name not in kwargs:
                kwargs[name] = default
        return kwargs

    def check(self):
        schema = (
            base_schema if self.strict else base_schema.extend({}, extra=ALLOW_EXTRA)
        )
        try:
            validate_schema(schema, self.copy(), "Invalid parameters:")
        except Exception as e:
            raise ParameterMismatch(str(e))

    def __getitem__(self, k):
        try:
            return super().__getitem__(k)
        except KeyError:
            raise KeyError(f"jobgraph parameter {k!r} not found")

    def is_try(self):
        """
        Determine whether this graph is being built on a try project or for
        `mach try fuzzy`.
        """
        return "try" in self["project"] or self["pipeline_source"] == "merge_request_event"

    def file_url(self, path, pretty=False):
        """
        Determine the VCS URL for viewing a file in the tree, suitable for
        viewing by a human.

        :param str path: The path, relative to the root of the repository.
        :param bool pretty: Whether to return a link to a formatted version of the
            file, or the raw file version.

        :return str: The URL displaying the given path.
        """
        # For getting the file URL for git repositories, we only support a Github HTTPS remote
        repo = self["head_repository"]
        repo_providers = [repo_provider for repo_provider in GIT_REPO_PROVIDERS if repo_provider in repo]
        if len(repo_providers) > 1:
            raise ParameterMismatch(f"Too many repo providers matched this repo: {repo}. Matched providers: {repo_providers}")
        elif len(repo_providers) == 0:
            raise ParameterMismatch(
                "Don't know how to determine file URL for non-github or non-gitlab"
                "repo: {}".format(repo)
            )

        repo_provider = repo_providers[0]
        if repo.startswith(f"https://{repo_provider}.com/"):
            if repo.endswith("/"):
                repo = repo[:-1]
            https_repo = repo
        elif repo.startswith(f"git@{repo_provider}.com:"):
            if repo.endswith(".git"):
                repo = repo[:-4]
            https_repo = repo.replace(f"git@{repo_provider}.com:", f"https://{repo_provider}.com/")
        else:
            raise ParameterMismatch(
                "Identified github or gitlab URL but cannot determine file URL. Repo: {repo}"
            )

        rev = self["head_rev"]
        endpoint = "blob" if pretty else "raw"
        separator = "/-" if repo_provider == "gitlab" else ""
        return f"{https_repo}{separator}/{endpoint}/{rev}/{path}"

    def __str__(self):
        return f"Parameters(id={self.id}) (from {self.format_spec(self.spec)})"

    def __repr__(self):
        return pformat(dict(self), indent=2)


def load_parameters_file(spec, strict=True, overrides=None, trust_domain=None):
    """
    Load parameters from a path, url, decision task-id or project.

    Examples:
        task-id=fdtgsD5DQUmAQZEaGMvQ4Q
        project=mozilla-central
    """
    from jobgraph.util.taskcluster import get_artifact_url
    from jobgraph.util import yaml

    if overrides is None:
        overrides = {}
    overrides["spec"] = spec

    if not spec:
        return Parameters(strict=strict, **overrides)

    try:
        # reading parameters from a local parameters.yml file
        f = open(spec)
    except OSError:
        # fetching parameters.yml using task task-id, project or supplied url
        task_id = None
        if spec.startswith("task-id="):
            task_id = spec.split("=")[1]
        elif spec.startswith("project="):
            if trust_domain is None:
                raise ValueError(
                    "Can't specify parameters by project "
                    "if trust domain isn't supplied.",
                )
        if task_id:
            spec = get_artifact_url(task_id, "public/parameters.yml")
        f = urlopen(spec)

    if spec.endswith(".yml"):
        kwargs = yaml.load_stream(f)
    elif spec.endswith(".json"):
        kwargs = json.load(f)
    else:
        raise TypeError(f"Parameters file `{spec}` is not JSON or YAML")

    kwargs.update(overrides)
    return Parameters(strict=strict, **kwargs)


def parameters_loader(spec, strict=True, overrides=None):
    def get_parameters(graph_config):
        parameters = load_parameters_file(
            spec,
            strict=strict,
            overrides=overrides,
            trust_domain=graph_config["trust-domain"],
        )
        parameters.check()
        return parameters

    return get_parameters
