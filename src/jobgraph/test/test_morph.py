# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import pytest

from jobgraph.config import DEFAULT_ROOT_DIR, load_graph_config
from jobgraph.graph import Graph
from jobgraph.jobgraph import JobGraph


@pytest.fixture(scope="module")
def graph_config():
    return load_graph_config(DEFAULT_ROOT_DIR)


@pytest.fixture
def make_jobgraph():
    def inner(tasks):
        graph = Graph(nodes=set(tasks), edges=set())
        jobgraph = JobGraph(tasks, graph)
        return jobgraph

    return inner
