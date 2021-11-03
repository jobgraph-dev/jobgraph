# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Support for running jobs that are invoked via the `run-task` script.
"""


import os
import shlex

import attr

from jobgraph.transforms.task import taskref_or_string
from jobgraph.transforms.job import run_job_using
from jobgraph.util import path
from jobgraph.util.schema import Schema
from jobgraph.transforms.job.common import support_vcs_checkout
from voluptuous import Required, Any, Optional

run_task_schema = Schema(
    {
        Required("using"): "run-task",
        # Whether or not to use caches.
        Optional("use-caches"): bool,
        # if true (the default), perform a checkout on the worker
        Required("checkout"): Any(bool, {str: dict}),
        Optional(
            "cwd",
            description="Path to run command in. If a checkout is present, the path "
            "to the checkout will be interpolated with the key `checkout`",
        ): str,
        # The command arguments to pass to the `run-task` script, after the
        # checkout arguments.  If a list, it will be passed directly; otherwise
        # it will be included in a single argument to `bash -cx`.
        Required("command"): Any([taskref_or_string], taskref_or_string),
        # Context to substitute into the command using format string
        # substitution (e.g {value}). This is useful if certain aspects of the
        # command need to be generated in transforms.
        Optional("command-context"): dict,
        # Base work directory used to set up the task.
        Required("workdir"): str,
        # Whether to run as root. (defaults to False)
        Optional("run-as-root"): bool,
    }
)


worker_defaults = {
    "checkout": True,
    "run-as-root": False,
}


@run_job_using(
    "kubernetes", "run-task", schema=run_task_schema, defaults=worker_defaults
)
def docker_worker_run_task(config, job, taskdesc):
    run = job["run"]
    worker = taskdesc["worker"] = job["worker"]
    # TODO Reuse "/usr/local/bin/run-task" whenever possible
    run_command = run["command"]

    command_context = run.get("command-context")
    if command_context:
        run_command = run_command.format(**command_context)

    worker["command"] = run_command
