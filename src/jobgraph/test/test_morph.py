# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import os

import pytest

from jobgraph.config import load_graph_config
from jobgraph.graph import Graph
from jobgraph.jobgraph import JobGraph


@pytest.fixture(scope="module")
def graph_config():
    return load_graph_config(os.path.join("gitlab-ci", "ci"))


@pytest.fixture
def make_jobgraph():
    def inner(tasks):
        for label in tasks:
            tasks[label].task_id = "TO-BE-REMOVED"
        graph = Graph(nodes=set(tasks), edges=set())
        jobgraph = JobGraph(tasks, graph)
        return jobgraph

    return inner
