from typing import AnyStr

import attr

from ..config import GraphConfig
from ..parameters import Parameters
from ..util.gitlab import extract_gitlab_instance_and_namespace_and_name
from ..util.memoize import memoize
from ..util.schema import Schema, validate_schema


@attr.s(frozen=True)
class RepoConfig:
    gitlab_instance_domain = attr.ib(type=str)
    name = attr.ib(type=str)
    namespace = attr.ib(type=str)
    base_repository = attr.ib(type=str)
    head_repository = attr.ib(type=str)
    head_ref = attr.ib(type=str)
    path = attr.ib(type=str, default="")
    head_rev = attr.ib(type=str, default=None)
    ssh_secret_name = attr.ib(type=str, default=None)


@attr.s(frozen=True, cmp=False)
class TransformConfig:
    """
    A container for configuration affecting transforms.  The `config` argument
    to transforms is an instance of this class.
    """

    # the name of the current stage
    stage = attr.ib()

    # the path to the stage configuration directory
    path = attr.ib(type=AnyStr)

    # the parsed contents of stage.yml
    config = attr.ib(type=dict)

    # the parameters for this task-graph generation run
    params = attr.ib(type=Parameters)

    # a list of all the jobs associated with the stage dependencies of the
    # current stage
    stage_upstream_dependencies_jobs = attr.ib()

    # Global configuration of the jobgraph
    graph_config = attr.ib(type=GraphConfig)

    # whether to write out artifacts for the decision task
    write_artifacts = attr.ib(type=bool)

    @property
    @memoize
    def repo_config(self):
        (
            gitlab_instance_domain,
            namespace,
            name,
        ) = extract_gitlab_instance_and_namespace_and_name(
            self.params["base_repository"]
        )

        return RepoConfig(
            gitlab_instance_domain=gitlab_instance_domain,
            name=name,
            namespace=namespace,
            base_repository=self.params["base_repository"],
            head_repository=self.params["head_repository"],
            head_ref=self.params["head_ref"],
            head_rev=self.params["head_rev"],
        )


@attr.s()
class TransformSequence:
    """
    Container for a sequence of transforms.  Each transform is represented as a
    callable taking (config, items) and returning a generator which will yield
    transformed items.  The resulting sequence has the same interface.

    This is convenient to use in a file full of transforms, as it provides a
    decorator, @transforms.add, that will add the decorated function to the
    sequence.
    """

    _transforms = attr.ib(factory=list)

    def __call__(self, config, items):
        for xform in self._transforms:
            items = xform(config, items)
            if items is None:
                raise Exception(f"Transform {xform} is not a generator")
        return items

    def add(self, func):
        self._transforms.append(func)
        return func

    def add_validate(self, schema):
        self.add(ValidateSchema(schema))


@attr.s
class ValidateSchema:
    schema = attr.ib(type=Schema)

    def __call__(self, config, jobs):
        for job in jobs:
            if "name" in job:
                error = f"In {config.stage} stage job {job['name']!r}:"
            elif "label" in job:
                error = f"In job {job['label']!r}:"
            elif "primary-dependency" in job:
                error = f"In {config.stage} stage job for {job['primary-dependency'].label!r}:"
            else:
                error = "In unknown job:"
            validate_schema(self.schema, job, error)
            yield job
