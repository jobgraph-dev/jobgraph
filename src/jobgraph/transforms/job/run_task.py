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


def common_setup(config, job, taskdesc, command):
    run = job["run"]
    if run["checkout"]:
        repo_configs = config.repo_configs
        if len(repo_configs) > 1 and run["checkout"] is True:
            raise Exception("Must explicitly sepcify checkouts with multiple repos.")
        elif run["checkout"] is not True:
            repo_configs = {
                repo: attr.evolve(repo_configs[repo], **config)
                for (repo, config) in run["checkout"].items()
            }

        vcs_path = support_vcs_checkout(
            config,
            job,
            taskdesc,
            repo_configs=repo_configs,
        )

        vcs_path = taskdesc["worker"]["env"]["VCS_PATH"]
        for repo_config in repo_configs.values():
            checkout_path = path.join(vcs_path, repo_config.path)
            command.append(f"--{repo_config.prefix}-checkout={checkout_path}")

        if "cwd" in run:
            run["cwd"] = path.normpath(run["cwd"].format(checkout=vcs_path))
    elif "cwd" in run and "{checkout}" in run["cwd"]:
        raise Exception(
            "Found `{{checkout}}` interpolation in `cwd` for task {name} "
            "but the task doesn't have a checkout: {cwd}".format(
                cwd=run["cwd"], name=job.get("name", job.get("label"))
            )
        )

    if "cwd" in run:
        command.extend(("--task-cwd", run["cwd"]))

    taskdesc["worker"].setdefault("env", {})["MOZ_SCM_LEVEL"] = config.params["level"]


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
    command = ["/usr/local/bin/run-task"]
    common_setup(config, job, taskdesc, command)

    run_command = run["command"]

    command_context = run.get("command-context")
    if command_context:
        run_command = run_command.format(**command_context)

    # dict is for the case of `{'task-reference': str}`.
    if isinstance(run_command, str) or isinstance(run_command, dict):
        run_command = ["bash", "-cx", run_command]
    if run["run-as-root"]:
        command.extend(("--user", "root", "--group", "root"))
    command.append("--")
    command.extend(run_command)
    worker["command"] = shlex.join(command)
