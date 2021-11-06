# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Graph morphs are modifications to task-graphs that take place *after* the
optimization phase.

These graph morphs are largely invisible to developers running `./mach`
locally, so they should be limited to changes that do not modify the meaning of
the graph.
"""

# Note that the translation of `{'task-reference': '..'}` and
# `artifact-reference` are handled in the optimization phase (since
# optimization involves dealing with taskIds directly).  Similarly,
# `{'relative-datestamp': '..'}` is handled at the last possible moment during
# task creation.


import logging
import os

from .graph import Graph
from .jobgraph import JobGraph

here = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def amend_jobgraph(jobgraph, to_add):
    """Add the given tasks to the jobgraph, returning a new jobgraph"""
    new_tasks = jobgraph.tasks.copy()
    new_edges = set(jobgraph.graph.edges)
    for task in to_add:
        new_tasks[task.task_id] = task
        for depname, dep in task.dependencies.items():
            new_edges.add((task.task_id, dep, depname))

    jobgraph = JobGraph(new_tasks, Graph(set(new_tasks), new_edges))
    return jobgraph


def morph(jobgraph, parameters, graph_config):
    """Apply all morphs"""
    morphs = []

    for m in morphs:
        jobgraph = m(jobgraph, parameters, graph_config)
    return jobgraph
