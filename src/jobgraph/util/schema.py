import collections
import pprint
import re

from voluptuous import (
    All,
    Any,
    Extra,
    MultipleInvalid,
    NotIn,
    Optional,
    Range,
    Required,
)
from voluptuous import Schema as VSchema
from voluptuous.validators import Length

import jobgraph
from jobgraph import MAX_UPSTREAM_DEPENDENCIES

from .keyed_by import evaluate_keyed_by


def validate_schema(schema, obj, msg_prefix):
    """
    Validate that object satisfies schema.  If not, generate a useful exception
    beginning with msg_prefix.
    """
    if jobgraph.fast:
        return
    try:
        schema(obj)
    except MultipleInvalid as exc:
        msg = [msg_prefix]
        for error in exc.errors:
            msg.append(str(error))
        raise Exception("\n".join(msg) + "\n" + pprint.pformat(obj))


def optionally_keyed_by(*arguments):
    """
    Mark a schema value as optionally keyed by any of a number of fields.  The
    schema is the last argument, and the remaining fields are taken to be the
    field names.  For example:

        'some-value': optionally_keyed_by(
            'test_platform', 'build-platform',
            Any('a', 'b', 'c'))

    The resulting schema will allow nesting of `by_test_platform` and
    `by_build_platform` in either order.
    """
    schema = arguments[-1]
    fields = arguments[:-1]

    # build the nestable schema by generating schema = Any(schema,
    # by_fld1, by_fld2, by_fld3) once for each field.  So we don't allow
    # infinite nesting, but one level of nesting for each field.
    for _ in arguments:
        options = [schema]
        for field in fields:
            options.append({"by_" + field: {str: schema}})
        schema = Any(*options)
    return schema


def resolve_keyed_by(item, field, item_name, **extra_values):
    """
    For values which can either accept a literal value, or be keyed by some
    other attribute of the item, perform that lookup and replacement in-place
    (modifying `item` directly).  The field is specified using dotted notation
    to traverse dictionaries.

    For example, given item::

        job:
            test_platform: linux128
            chunks:
                by_test_platform:
                    macosx-10.11/debug: 13
                    win.*: 6
                    default: 12

    a call to `resolve_keyed_by(item, 'job.chunks', item['thing-name'])`
    would mutate item in-place to::

        job:
            test_platform: linux128
            chunks: 12

    The `item_name` parameter is used to generate useful error messages.

    If extra_values are supplied, they represent additional values available
    for reference from by_<field>.

    Items can be nested as deeply as the schema will allow::

        chunks:
            by_test_platform:
                win.*: 10
                linux: 13
                default: 12
    """
    # find the field, returning the item unchanged if anything goes wrong
    container, subfield = item, field
    while "." in subfield:
        f, subfield = subfield.split(".", 1)
        if f not in container:
            return item
        container = container[f]
        if not isinstance(container, dict):
            return item

    if subfield not in container:
        return item

    container[subfield] = evaluate_keyed_by(
        value=container[subfield],
        item_name=f"`{field}` in `{item_name}`",
        attributes=dict(item, **extra_values),
    )

    return item


def check_schema(schema):
    identifier_re = re.compile("^[a-z][a-z0-9_]*$")

    def iter(path, sch):
        def check_identifier(path, k):
            if k in (str,) or k in (str, Extra):
                pass
            elif isinstance(k, NotIn):
                pass
            elif isinstance(k, str):
                if not identifier_re.match(k):
                    raise RuntimeError(
                        "YAML schemas should use underscored lower-case identifiers, "
                        f"not {k!r} @ {path}"
                    )
            elif isinstance(k, (Optional, Required)):
                check_identifier(path, k.schema)
            elif isinstance(k, (Any, All)):
                for v in k.validators:
                    check_identifier(path, v)
            else:
                raise RuntimeError(
                    f"Unexpected type in YAML schema: {type(k).__name__} @ {path}"
                )

        if isinstance(sch, collections.abc.Mapping):
            for k, v in sch.items():
                child = f"{path}[{k!r}]"
                check_identifier(child, k)
                iter(child, v)
        elif isinstance(sch, (list, tuple)):
            for i, v in enumerate(sch):
                iter(f"{path}[{i}]", v)
        elif isinstance(sch, Any):
            for v in sch.validators:
                iter(path, v)

    iter("schema", schema.schema)


class Schema(VSchema):
    """
    Operates identically to voluptuous.Schema, but applying some
    jobgraph-specific checks in the process.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        check_schema(self)

    def extend(self, *args, **kwargs):
        schema = super().extend(*args, **kwargs)
        check_schema(schema)
        # We want twice extend schema to be checked too.
        schema.__class__ = Schema
        return schema

    def __getitem__(self, item):
        return self.schema[item]


# shortcut for a string where task references are allowed
docker_image_ref = Any(
    # strings are now allowed because we want to keep track of external
    # images in config.yml
    #
    # an external docker image defined in config.yml
    {"docker_image_reference": str},
    # an in_tree generated docker image (from `gitlab-ci/docker/<name>`)
    {"in_tree": str},
)

str_or_list_of_str = Any(
    str,
    [str],
)

when_def = Any("on_success", "on_failure", "always")

secret_def = {
    Required("vault"): Any(
        str,
        {
            Required("engine"): {
                Required("name"): str,
                Required("path"): str,
            },
            Required("path"): str,
            Required("field"): str,
        },
    ),
    Optional("file"): bool,
}

cache_def = {
    Required("key"): Any(
        str,
        {
            Required("files"): [str],
            Optional("prefix"): str,
        },
    ),
    Required("paths"): [str],
    Optional("policy"): Any("pull", "push", "pull-push"),
    Optional("untracked"): bool,
    Optional("when"): when_def,
}

# Source https://docs.gitlab.com/ee/ci/yaml/index.html
gitlab_ci_job_common = Schema(
    {
        Optional("after_script"): str_or_list_of_str,
        Optional("allow_failure"): Any(bool, {"exit_codes": Any(int, [int])}),
        Optional("artifacts"): {
            Optional("exclude"): [str],
            Optional("expire_in"): str,
            Optional("expose_as"): str,
            Optional("name"): str,
            Required("paths"): [str],
            Optional("public"): bool,
            # TODO Be more restrictive for reports
            # https://docs.gitlab.com/ee/ci/yaml/artifacts_reports.html
            Optional("reports"): dict,
            Optional("untracked"): bool,
            Optional("when"): when_def,
        },
        Optional("before_script"): str_or_list_of_str,
        Optional("cache"): cache_def,
        Optional("coverage"): str,
        Optional("dast_configuration"): {
            Required("site_profile"): str,
            Required("scanner_profile"): str,
        },
        Optional("environment"): Any(
            str,
            {
                Optional("action"): Any("prepare", "start", "stop"),
                Optional("auto_stop_in"): str,
                Optional("deployment_tier"): Any(
                    "production", "staging", "testing", "development", "other"
                ),
                Required("name"): str,
                Optional("on_stop"): str,
                Optional("url"): str,
            },
        ),
        Required("image"): Any(
            docker_image_ref,
            {
                Required("name"): docker_image_ref,
                Optional("entrypoint"): str_or_list_of_str,
            },
        ),
        Optional("interruptible"): bool,
        Optional("parallel"): Any(Range(2, 50), {Required("matrix"): [dict]}),
        Optional("release"): {
            Required("assets"): {
                Required("links"): [
                    {
                        Required("name"): str,
                        Required("url"): str,
                        Optional("filepath"): str,
                        Optional("link_type"): Any(
                            "runbook", "package", "image", "other"
                        ),
                    }
                ],
            },
            Required("description"): str,
            Optional("name"): str,
            Optional("ref"): str,
            Optional("milestones"): str,
            Optional("released_at"): str,
            Required("tag_name"): str,
        },
        Optional("resource_group"): str,
        Optional("retry"): Any(
            Range(0, 2),
            {
                Required("max"): Range(0, 2),
                Optional("when"): [
                    Any(
                        "always",
                        "unknown_failure",
                        "script_failure",
                        "api_failure",
                        "stuck_or_timeout_failure",
                        "runner_system_failure",
                        "runner_unsupported",
                        "stale_schedule",
                        "job_execution_timeout",
                        "archived_failure",
                        "unmet_prerequisites",
                        "scheduler_failure",
                        "data_integrity_failure",
                    )
                ],
            },
        ),
        Optional("schedules"): dict,
        Optional("script"): str_or_list_of_str,
        Optional("secrets"): {
            str: secret_def,
        },
        Optional("services"): [docker_image_ref],
        Optional("timeout"): str,
        Optional("trigger"): Any(
            str,
            {
                Required("include"): str,
                Optional("strategy"): Any("depend"),
            },
        ),
        Optional("variables"): {
            str: Any(
                int,
                str,
                docker_image_ref,
                {
                    Required("value"): Any(int, str, docker_image_ref),
                    Optional("description"): str,
                },
            ),
        },
    }
)

gitlab_ci_job_input = gitlab_ci_job_common.extend(
    {
        Required("label"): str,
        Required("description"): str,
        Optional("attributes"): {str: object},
        # relative path (from config.path) to the file this job was defined in
        Optional("job_from"): str,
        # upstream dependencies of this job, keyed by name; these are passed through
        # verbatim.
        Optional("upstream_dependencies"): {
            All(
                str,
                NotIn(
                    ["self"],
                    "Can't use 'self` as depdency names.",
                ),
            ): object,
        },
        Required("image"): docker_image_ref,
        Optional("run_on_pipeline_sources"): [str],
        Optional("run_on_git_branches"): [str],
        # The `always_target` attribute will cause the job to be included in the
        # target_job_graph regardless of filtering. Jobs included in this manner
        # will be candidates for optimization even when `optimize_target_jobs` is
        # False, unless the job was also explicitly chosen by the target_jobs
        # method.
        Optional("always_target"): bool,
        # Optimization to perform on this job during the optimization phase.
        # Optimizations are defined in gitlab-ci/jobgraph/optimize.py.
        Optional("optimization"): dict,
        # the runner_alias for the job. Will be substituted into an actual Gitlab
        # CI tag.
        "runner_alias": str,
    }
)

gitlab_ci_job_output = gitlab_ci_job_common.extend(
    {
        Optional("upstream_dependencies"): [str],
        Required("image"): str,
        Optional("needs"): All(
            [
                Any(
                    str,
                    {
                        Required("job"): str,
                        Optional("artifacts"): bool,
                        Optional("optional"): bool,
                        Optional("pipeline"): int,
                        Optional("project"): str,
                        Optional("ref"): str,
                    },
                )
            ],
            Length(max=MAX_UPSTREAM_DEPENDENCIES),
        ),
        Optional("services"): [str],
        Required("stage"): str,
        Required("tags"): All(
            [str],
            Length(
                max=1,
                msg="For the sake of reproducibility, please use only a single tag "
                "to identify a runner. Multiple tags are a potential footgun. You "
                "may end up running your job on an unexpected runner.",
            ),
        ),
        Optional("variables"): {
            str: Any(
                int,
                str,
                {
                    Required("value"): Any(int, str),
                    Optional("description"): str,
                },
            ),
        },
    }
)
