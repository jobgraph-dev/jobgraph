# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import logging

import attr

logger = logging.getLogger(__name__)


@attr.s(frozen=True)
class VerificationSequence:
    """
    Container for a sequence of verifications over a JobGraph. Each
    verification is represented as a callable taking (task, jobgraph,
    scratch_pad), called for each task in the jobgraph, and one more
    time with no task but with the jobgraph and the same scratch_pad
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


@verifications.add("optimized_job_graph")
def verify_always_optimized(task, jobgraph, scratch_pad, graph_config):
    """
    This function ensures that always-optimized jobs have been optimized.
    """
    if task is None:
        return
    if task.actual_gitlab_ci_job.get("workerType") == "always-optimized":
        raise Exception(f"Could not optimize the task {task.label!r}")
