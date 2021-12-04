import pytest

from jobgraph.config import DEFAULT_ROOT_DIR, load_graph_config
from jobgraph.graph import Graph
from jobgraph.jobgraph import JobGraph


@pytest.fixture(scope="module")
def graph_config():
    return load_graph_config(DEFAULT_ROOT_DIR)


@pytest.fixture
def make_jobgraph():
    def inner(jobs):
        graph = Graph(nodes=set(jobs), edges=set())
        jobgraph = JobGraph(jobs, graph)
        return jobgraph

    return inner
