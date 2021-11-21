# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


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
from jobgraph import MAX_DEPENDENCIES

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
            'test-platform', 'build-platform',
            Any('a', 'b', 'c'))

    The resulting schema will allow nesting of `by-test-platform` and
    `by-build-platform` in either order.
    """
    schema = arguments[-1]
    fields = arguments[:-1]

    # build the nestable schema by generating schema = Any(schema,
    # by-fld1, by-fld2, by-fld3) once for each field.  So we don't allow
    # infinite nesting, but one level of nesting for each field.
    for _ in arguments:
        options = [schema]
        for field in fields:
            options.append({"by-" + field: {str: schema}})
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
            test-platform: linux128
            chunks:
                by-test-platform:
                    macosx-10.11/debug: 13
                    win.*: 6
                    default: 12

    a call to `resolve_keyed_by(item, 'job.chunks', item['thing-name'])`
    would mutate item in-place to::

        job:
            test-platform: linux128
            chunks: 12

    The `item_name` parameter is used to generate useful error messages.

    If extra_values are supplied, they represent additional values available
    for reference from by-<field>.

    Items can be nested as deeply as the schema will allow::

        chunks:
            by-test-platform:
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


# Schemas for YAML files should use dashed identifiers by default.  If there are
# components of the schema for which there is a good reason to use another format,
# they can be whitelisted here.
WHITELISTED_SCHEMA_IDENTIFIERS = [
    # upstream-artifacts and artifact-map are handed directly to scriptWorker,
    # which expects interCaps
    lambda path: any(
        exc in path for exc in ("['upstream-artifacts']", "['artifact-map']")
    )
]


def check_schema(schema):
    identifier_re = re.compile("^[a-z][a-z0-9-_]*$")

    def whitelisted(path):
        return any(f(path) for f in WHITELISTED_SCHEMA_IDENTIFIERS)

    def iter(path, sch):
        def check_identifier(path, k):
            if k in (str,) or k in (str, Extra):
                pass
            elif isinstance(k, NotIn):
                pass
            elif isinstance(k, str):
                if not identifier_re.match(k) and not whitelisted(path):
                    raise RuntimeError(
                        "YAML schemas should use dashed/underscored lower-case identifiers, "
                        f"not {k!r} @ {path}"
                    )
            elif isinstance(k, (Optional, Required)):
                check_identifier(path, k.schema)
            elif isinstance(k, (Any, All)):
                for v in k.validators:
                    check_identifier(path, v)
            elif not whitelisted(path):
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
    Operates identically to voluptuous.Schema, but applying some jobgraph-specific checks
    in the process.
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
    {"docker-image-reference": str},
    # an in-tree generated docker image (from `gitlab-ci/docker/<name>`)
    {"in-tree": str},
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
        Optional("cache"): {
            Optional("key"): Any(
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
        },
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
                        Optional("link_typ"): Any(
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
        Optional("job-from"): str,
        # dependencies of this job, keyed by name; these are passed through
        # verbatim and subject to the interpretation of the Job's get_dependencies
        # method.
        Optional("dependencies"): {
            All(
                str,
                NotIn(
                    ["self", "decision"],
                    "Can't use 'self` or 'decision' as depdency names.",
                ),
            ): object,
        },
        Required("image"): docker_image_ref,
        Optional("run-on-pipeline-sources"): [str],
        Optional("run-on-git-branches"): [str],
        # The `always-target` attribute will cause the job to be included in the
        # target_job_graph regardless of filtering. Jobs included in this manner
        # will be candidates for optimization even when `optimize_target_jobs` is
        # False, unless the job was also explicitly chosen by the target_jobs
        # method.
        Required("always-target"): bool,
        # Optimization to perform on this job during the optimization phase.
        # Optimizations are defined in gitlab-ci/jobgraph/optimize.py.
        Optional("optimization"): dict,
        # the runner-alias for the job. Will be substituted into an actual Gitlab
        # CI tag.
        "runner-alias": str,
    }
)

gitlab_ci_job_output = gitlab_ci_job_common.extend(
    {
        Optional("dependencies"): [str],
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
            Length(max=MAX_DEPENDENCIES),
        ),
        Required("stage"): str,
        Required("tags"): All([str, Length(max=1)]),
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
