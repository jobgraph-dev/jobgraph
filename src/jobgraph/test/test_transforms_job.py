# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Tests for the 'job' transform subsystem.
"""


import os
from copy import deepcopy

import pytest

from jobgraph.config import load_graph_config
from jobgraph.transforms import job
from jobgraph.transforms.job import run_task  # noqa: F401
from jobgraph.transforms.base import TransformConfig

from .conftest import FakeParameters

here = os.path.abspath(os.path.dirname(__file__))


TASK_DEFAULTS = {
    "description": "fake description",
    "label": "fake-task-label",
    "run": {
        "using": "run-task",
    },
}


@pytest.fixture(scope="module")
def config():
    graph_config = load_graph_config(os.path.join("gitlab-ci", "ci"))
    params = FakeParameters(
        {
            "base_repository": "http://gitlab.example.com",
            "head_repository": "http://gitlab.example.com",
            "head_rev": "abcdef",
            "head_ref": "abcdef",
            "level": 1,
        }
    )
    return TransformConfig(
        "job_test", here, {}, params, {}, graph_config, write_artifacts=False
    )


@pytest.fixture()
def transform(monkeypatch, config):
    """Run the job transforms on the specified task but return the inputs to
    `configure_taskdesc_for_run` without executing it.

    This gives test functions an easy way to generate the inputs required for
    many of the `run_using` subsystems.
    """

    def inner(task_input):
        task = deepcopy(TASK_DEFAULTS)
        task.update(task_input)
        frozen_args = []

        def _configure_taskdesc_for_run(*args):
            frozen_args.extend(args)

        monkeypatch.setattr(
            job, "configure_taskdesc_for_run", _configure_taskdesc_for_run
        )

        for _ in job.transforms(config, [task]):
            # This forces the generator to be evaluated
            pass

        return frozen_args

    return inner


@pytest.mark.parametrize(
    "workerfn", [fn for fn, *_ in job.registry["run-task"].values()]
)
@pytest.mark.parametrize(
    "task",
    (
        {
            "worker-type": "t-linux",
            "run": {
                "checkout": True,
                "comm-checkout": False,
                "command": "echo '{output}'",
                "command-context": {"output": "hello", "extra": None},
                "run-as-root": False,
                "tooltool-downloads": False,
            },
        },
    ),
)
def test_run_task_command_context(task, transform, workerfn):
    config, job_, taskdesc, _ = transform(task)
    job_ = deepcopy(job_)

    def assert_cmd(expected):
        cmd = taskdesc["worker"]["command"]
        while isinstance(cmd, list):
            cmd = cmd[-1]
        assert cmd == expected

    workerfn(config, job_, taskdesc)
    assert_cmd("echo 'hello'")

    job_copy = job_.copy()
    del job_copy["run"]["command-context"]
    workerfn(config, job_copy, taskdesc)
    assert_cmd("echo '{output}'")
