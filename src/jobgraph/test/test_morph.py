# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import os

import pytest

from jobgraph import morph
from jobgraph.config import load_graph_config
from jobgraph.graph import Graph
from jobgraph.parameters import Parameters
from jobgraph.jobgraph import JobGraph
from jobgraph.job import Job


@pytest.fixture(scope="module")
def graph_config():
    return load_graph_config(os.path.join("taskcluster", "ci"))


@pytest.fixture
def make_taskgraph():
    def inner(tasks):
        label_to_taskid = {k: k + "-tid" for k in tasks}
        for label, task_id in label_to_taskid.items():
            tasks[label].task_id = task_id
        graph = Graph(nodes=set(tasks), edges=set())
        taskgraph = JobGraph(tasks, graph)
        return taskgraph, label_to_taskid

    return inner
