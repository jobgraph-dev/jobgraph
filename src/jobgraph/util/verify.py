# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import logging
import sys

import attr

logger = logging.getLogger(__name__)


@attr.s(frozen=True)
class VerificationSequence:
    """
    Container for a sequence of verifications over a TaskGraph. Each
    verification is represented as a callable taking (task, taskgraph,
    scratch_pad), called for each task in the taskgraph, and one more
    time with no task but with the taskgraph and the same scratch_pad
    that was passed for each task.
    """

    _verifications = attr.ib(factory=dict)

    def __call__(self, graph_name, graph, graph_config):
        for verification in self._verifications.get(graph_name, []):
            scratch_pad = {}
            graph.for_each_job(
                verification, scratch_pad=scratch_pad, graph_config=graph_config
            )
            verification(
                None, graph, scratch_pad=scratch_pad, graph_config=graph_config
            )
        return graph_name, graph

    def add(self, graph_name):
        def wrap(func):
            self._verifications.setdefault(graph_name, []).append(func)
            return func

        return wrap


verifications = VerificationSequence()


@verifications.add("full_task_graph")
def verify_notification_filters(task, taskgraph, scratch_pad, graph_config):
    """
    This function ensures that only understood filters for notifications are
    specified.

    See: https://docs.taskcluster.net/reference/core/taskcluster-notify/docs/usage
    """
    if task is None:
        return
    valid_filters = ("on-any", "on-completed", "on-failed", "on-exception")
    task_dict = task.task

    # TODO support notification without Taskcluster's routes


@verifications.add("optimized_task_graph")
def verify_always_optimized(task, taskgraph, scratch_pad, graph_config):
    """
    This function ensures that always-optimized tasks have been optimized.
    """
    if task is None:
        return
    if task.task.get("workerType") == "always-optimized":
        raise Exception(f"Could not optimize the task {task.label!r}")
