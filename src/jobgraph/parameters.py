# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import hashlib
import json
import logging
import os
import time
from pprint import pformat
from urllib.parse import urlparse
from urllib.request import urlopen

from voluptuous import ALLOW_EXTRA, Required, Schema

from jobgraph.util.memoize import memoize
from jobgraph.util.readonlydict import ReadOnlyDict
from jobgraph.util.schema import validate_schema
from jobgraph.util.vcs import NULL_GIT_COMMIT, get_repository

logger = logging.getLogger(__name__)


class ParameterMismatch(Exception):
    """Raised when a parameters.yml has extra or missing parameters."""


@memoize
def get_repo():
    return get_repository(os.getcwd())


# Please keep this list sorted and in sync with taskcluster/docs/parameters.rst
base_schema = Schema(
    {
        Required("base_repository"): str,
        Required("base_rev"): str,
        Required("build_date"): int,
        Required("do_not_optimize"): [str],
        Required("filters"): [str],
        Required("head_ref"): str,
        Required("head_ref_protection"): str,
        Required("head_repository"): str,
        Required("head_rev"): str,
        Required("head_tag"): str,
        Required("optimize_target_jobs"): bool,
        Required("owner"): str,
        # target-stage is not included, since it should never be
        # used at run-time
        Required("target_jobs_method"): str,
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

        kwargs = _determine_base_rev(kwargs)

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

        if spec.startswith("task-id="):
            return spec

        result = urlparse(spec)
        if result.scheme in ("http", "https"):
            spec = result.path

        return os.path.splitext(os.path.basename(spec))[0]

    @staticmethod
    def _fill_defaults(**kwargs):
        defaults = {
            "base_repository": get_repo().get_url(),
            "base_rev": "0",  # TODO
            "build_date": int(time.time()),
            "do_not_optimize": [],
            "filters": ["target_jobs_method"],
            "head_ref": get_repo().head_ref,
            "head_ref_protection": "protected",  # main branch is protected by default
            "head_repository": get_repo().get_url(),
            "head_rev": get_repo().head_ref,
            "head_tag": "",
            "optimize_target_jobs": True,
            "owner": "nobody@mozilla.com",
            "target_jobs_method": "default",
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
        return self["pipeline_source"] == "merge_request_event"

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
        repo_providers = [
            repo_provider
            for repo_provider in GIT_REPO_PROVIDERS
            if repo_provider in repo
        ]
        if len(repo_providers) > 1:
            raise ParameterMismatch(
                f"Too many repo providers matched this repo: {repo}. "
                "Matched providers: {repo_providers}"
            )
        elif len(repo_providers) == 0:
            raise ParameterMismatch(
                f"Don't know how to determine file URL for non-github or non-gitlabrepo: {repo}"
            )

        repo_provider = repo_providers[0]
        if repo.startswith(f"https://{repo_provider}.com/"):
            if repo.endswith("/"):
                repo = repo[:-1]
            https_repo = repo
        elif repo.startswith(f"git@{repo_provider}.com:"):
            if repo.endswith(".git"):
                repo = repo[:-4]
            https_repo = repo.replace(
                f"git@{repo_provider}.com:", f"https://{repo_provider}.com/"
            )
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


def _determine_base_rev(kwargs):
    if kwargs.get("base_rev") == NULL_GIT_COMMIT:
        logger.info(
            f'base_rev equals "{NULL_GIT_COMMIT}". Finding the most common ancestor...'
        )
        if kwargs["base_repository"] != kwargs["head_repository"]:
            # TODO Clone the base repo to determine the first common
            # ancestor revision
            raise NotImplementedError(
                "Cannot yet determine what files have changed between base "
                f'repository ({kwargs["base_repository"]} and head one '
                f'({kwargs["head_repository"]}))'
            )

        repo = get_repo()
        # Gitlab runners check out a detached HEAD which prevents us
        # from getting the remote repository of the kwargs["head_ref"]
        # branch. Thus, we have to rely on the fact that "origin" is
        # the only remote
        main_branch = repo.get_main_branch()
        kwargs["base_rev"] = repo.find_first_common_revision(
            main_branch, kwargs["head_rev"]
        )
        logger.info(f'base_rev has been set to "{kwargs["base_rev"]}"')

    return kwargs


def load_parameters_file(spec, strict=True, overrides=None):
    """
    Load parameters from a path, url, decision task-id.

    Examples:
        task-id=fdtgsD5DQUmAQZEaGMvQ4Q
    """
    from jobgraph.util import yaml
    from jobgraph.util.taskcluster import get_artifact_url

    if overrides is None:
        overrides = {}
    overrides["spec"] = spec

    if not spec:
        return Parameters(strict=strict, **overrides)

    try:
        # reading parameters from a local parameters.yml file
        f = open(spec)
    except OSError:
        # fetching parameters.yml using task task-id or supplied url
        task_id = None
        if spec.startswith("task-id="):
            task_id = spec.split("=")[1]
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
        )
        parameters.check()
        return parameters

    return get_parameters
