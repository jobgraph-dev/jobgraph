# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import unittest

from jobgraph.graph import Graph
from jobgraph.job import Job
from jobgraph.jobgraph import JobGraph


class TestJobGraph(unittest.TestCase):

    maxDiff = None

    def test_jobgraph_to_json(self):
        tasks = {
            "a": Job(
                kind="test",
                label="a",
                description="some test a",
                attributes={"attr": "a-task"},
                actual_gitlab_ci_job={"taskdef": True},
            ),
            "b": Job(
                kind="test",
                label="b",
                description="some test b",
                attributes={},
                actual_gitlab_ci_job={"task": "def"},
                optimization={"seta": None},
                # note that this dep is ignored, superseded by that
                # from the jobgraph's edges
                dependencies={"first": "a"},
            ),
        }
        graph = Graph(nodes=set("ab"), edges={("a", "b", "edgelabel")})
        jobgraph = JobGraph(tasks, graph)

        res = jobgraph.to_json()

        self.assertEqual(
            res,
            {
                "a": {
                    "kind": "test",
                    "label": "a",
                    "description": "some test a",
                    "attributes": {"attr": "a-task", "kind": "test"},
                    "actual_gitlab_ci_job": {"taskdef": True},
                    "dependencies": {"edgelabel": "b"},
                    "soft_dependencies": [],
                    "optimization": None,
                },
                "b": {
                    "kind": "test",
                    "label": "b",
                    "description": "some test b",
                    "attributes": {"kind": "test"},
                    "actual_gitlab_ci_job": {"task": "def"},
                    "dependencies": {},
                    "soft_dependencies": [],
                    "optimization": {"seta": None},
                },
            },
        )

    def test_round_trip(self):
        graph = JobGraph(
            jobs={
                "a": Job(
                    kind="fancy",
                    label="a",
                    description="some fancy a",
                    attributes={},
                    dependencies={"prereq": "b"},  # must match edges, below
                    optimization={"seta": None},
                    actual_gitlab_ci_job={"task": "def"},
                ),
                "b": Job(
                    kind="pre",
                    label="b",
                    description="some pre b",
                    attributes={},
                    dependencies={},
                    optimization={"seta": None},
                    actual_gitlab_ci_job={"task": "def2"},
                ),
            },
            graph=Graph(nodes={"a", "b"}, edges={("a", "b", "prereq")}),
        )

        tasks, new_graph = JobGraph.from_json(graph.to_json())
        self.assertEqual(graph, new_graph)

    simple_graph = JobGraph(
        jobs={
            "a": Job(
                kind="fancy",
                label="a",
                description="some fancy a",
                attributes={},
                dependencies={"prereq": "b"},  # must match edges, below
                optimization={"seta": None},
                actual_gitlab_ci_job={"task": "def"},
            ),
            "b": Job(
                kind="pre",
                label="b",
                description="some pre b",
                attributes={},
                dependencies={},
                optimization={"seta": None},
                actual_gitlab_ci_job={"task": "def2"},
            ),
        },
        graph=Graph(nodes={"a", "b"}, edges={("a", "b", "prereq")}),
    )

    def test_contains(self):
        assert "a" in self.simple_graph
        assert "c" not in self.simple_graph
