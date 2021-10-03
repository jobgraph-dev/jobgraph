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
import re

from slugid import nice as slugid

from .job import Job
from .graph import Graph
from .jobgraph import JobGraph
from .util.workertypes import get_worker_type

here = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def amend_taskgraph(taskgraph, label_to_taskid, to_add):
    """Add the given tasks to the taskgraph, returning a new taskgraph"""
    new_tasks = taskgraph.tasks.copy()
    new_edges = set(taskgraph.graph.edges)
    for task in to_add:
        new_tasks[task.task_id] = task
        assert task.label not in label_to_taskid
        label_to_taskid[task.label] = task.task_id
        for depname, dep in task.dependencies.items():
            new_edges.add((task.task_id, dep, depname))

    taskgraph = JobGraph(new_tasks, Graph(set(new_tasks), new_edges))
    return taskgraph, label_to_taskid


def derive_index_task(task, taskgraph, label_to_taskid, parameters, graph_config):
    """Create the shell of a task that depends on `task` and on the given docker
    image."""
    purpose = "index-task"
    label = f"{purpose}-{task.label}"
    provisioner_id, worker_type = get_worker_type(
        graph_config, "misc", parameters["level"]
    )

    task_def = {
        "provisionerId": provisioner_id,
        "workerType": worker_type,
        "dependencies": [task.task_id],
        "created": {"relative-datestamp": "0 seconds"},
        "deadline": task.task["deadline"],
        # no point existing past the parent task's deadline
        "expires": task.task["deadline"],
        "metadata": {
            "name": label,
            "description": "{} for {}".format(
                purpose, task.task["metadata"]["description"]
            ),
            "owner": task.task["metadata"]["owner"],
            "source": task.task["metadata"]["source"],
        },
        "payload": {
            "image": {
                "path": "public/image.tar.zst",
                "namespace": "taskgraph.cache.level-3.docker-images.v2.index-task.latest",
                "type": "indexed-image",
            },
            "features": {
                "taskclusterProxy": True,
            },
            "maxRunTime": 600,
        },
    }

    # only include the docker-image dependency here if it is actually in the
    # taskgraph (has not been optimized).  It is included in
    # task_def['dependencies'] unconditionally.
    dependencies = {"parent": task.task_id}

    task = Job(
        kind="misc",
        label=label,
        attributes={},
        task=task_def,
        dependencies=dependencies,
    )
    task.task_id = slugid()
    return task, taskgraph, label_to_taskid


def _get_morph_url():
    """
    Guess a URL for the current file, for source metadata for created tasks.

    If we checked out the taskgraph code with run-task in the decision task,
    we can use TASKGRAPH_* to find the right version, which covers the
    existing use case.
    """
    taskgraph_repo = os.environ.get(
        "TASKGRAPH_HEAD_REPOSITORY", "https://hg.mozilla.org/ci/taskgraph"
    )
    taskgraph_rev = os.environ.get("TASKGRAPH_HEAD_REV", "default")
    return f"{taskgraph_repo}/raw-file/{taskgraph_rev}/src/jobgraph/morph.py"


def morph(taskgraph, label_to_taskid, parameters, graph_config):
    """Apply all morphs"""
    morphs = [
        add_index_tasks,
    ]

    for m in morphs:
        taskgraph, label_to_taskid = m(
            taskgraph, label_to_taskid, parameters, graph_config
        )
    return taskgraph, label_to_taskid
