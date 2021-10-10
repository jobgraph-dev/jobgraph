# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import unittest

from jobgraph import target_tasks
from jobgraph.graph import Graph
from jobgraph.jobgraph import JobGraph
from jobgraph.job import Job


class TestTargetTasks(unittest.TestCase):
    def default_matches_project(self, project):
        return self.default_matches(
            attributes={},
            parameters={
                "project": project,
                "pipeline_source": "push",
            },
        )

    def default_matches_pipeline_source(self, pipeline_source):
        attributes = {}

        return self.default_matches(
            attributes=attributes,
            parameters={
                "project": "mozilla-central",
                "pipeline_source": pipeline_source,
            },
        )

    def default_matches_git_branches(
        self, run_on_pipeline_sources, pipeline_source, run_on_git_branches, git_branch
    ):
        attributes = {
            "run_git_branches": ["all"],
        }
        if run_on_pipeline_sources is not None:
            attributes["run_on_pipeline_sources"] = run_on_pipeline_sources
        if run_on_git_branches is not None:
            attributes["run_on_git_branches"] = run_on_git_branches

        return self.default_matches(
            attributes=attributes,
            parameters={
                "project": "fenix",
                "pipeline_source": pipeline_source,
                "head_ref": git_branch,
            },
        )

    def default_matches(self, attributes, parameters):
        method = target_tasks.get_method("default")
        graph = JobGraph(
            jobs={
                "a": Job(kind="build", label="a", attributes=attributes, actual_gitlab_ci_job={}),
            },
            graph=Graph(nodes={"a"}, edges=set()),
        )
        return "a" in method(graph, parameters, {})

    def test_default_pipeline_source(self):
        self.assertTrue(self.default_matches_pipeline_source(None, "push"))
        self.assertTrue(self.default_matches_pipeline_source(None, "merge_request_event"))

        self.assertFalse(self.default_matches_pipeline_source([], "push"))
        self.assertFalse(self.default_matches_pipeline_source([], "merge_request_event"))

        self.assertTrue(self.default_matches_pipeline_source(["all"], "push"))
        self.assertTrue(self.default_matches_pipeline_source(["all"], "merge_request_event"))

        self.assertTrue(self.default_matches_pipeline_source(["push"], "push"))
        self.assertFalse(
            self.default_matches_pipeline_source(["push"], "merge_request_event")
        )

        self.assertTrue(
            self.default_matches_pipeline_source(
                ["merge_request_event"], "merge_request_event"
            )
        )
        self.assertFalse(
            self.default_matches_pipeline_source(["merge_request_event"], "push")
        )

    def test_default_git_branches(self):
        self.assertTrue(
            self.default_matches_git_branches(
                None, "merge_request_event", None, "master"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                None, "merge_request_event", None, "some-branch"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(None, "push", None, "master")
        )
        self.assertTrue(
            self.default_matches_git_branches(None, "push", None, "main")
        )
        self.assertTrue(
            self.default_matches_git_branches(None, "push", None, "some-branch")
        )
        self.assertTrue(
            self.default_matches_git_branches(
                None, "push", None, "release/v1.0"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                None, "push", None, "release_v2.0"
            )
        )

        self.assertFalse(
            self.default_matches_git_branches([], "merge_request_event", None, "master")
        )
        self.assertFalse(
            self.default_matches_git_branches(
                [], "merge_request_event", None, "some-branch"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches([], "push", None, "master")
        )
        self.assertFalse(
            self.default_matches_git_branches([], "push", None, "main")
        )
        self.assertFalse(
            self.default_matches_git_branches([], "push", None, "some-branch")
        )
        self.assertFalse(
            self.default_matches_git_branches([], "push", None, "master")
        )
        self.assertFalse(
            self.default_matches_git_branches(
                [], "push", None, "release/v1.0"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                [], "push", None, "release_v2.0"
            )
        )

        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "merge_request_event", ["master"], "master"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "merge_request_event", ["master"], "some-branch"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "push", ["master"], "master"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", ["master"], "main"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", ["master"], "some-branch"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "push", ["master"], "master"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", ["master"], "release/v1.0"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", ["master"], "release_v2.0"
            )
        )

        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "merge_request_event", [r"release/.+"], "master"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "merge_request_event", [r"release/.+"], "some-branch"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", [r"release/.+"], "master"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", [r"release/.+"], "main"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", [r"release/.+"], "some-branch"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", [r"release/.+"], "master"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "push", [r"release/.+"], "release/v1.0"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", [r"release/.+"], "release_v2.0"
            )
        )

        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "merge_request_event", [r"release/.+"], "refs/heads/master"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"],
                "merge_request_event",
                [r"release/.+"],
                "refs/heads/some-branch",
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", [r"release/.+"], "refs/heads/master"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", [r"release/.+"], "refs/heads/main"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", [r"release/.+"], "refs/heads/some-branch"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", [r"release/.+"], "refs/heads/master"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "push", [r"release/.+"], "refs/heads/release/v1.0"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", [r"release/.+"], "refs/heads/release_v2.0"
            )
        )

        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "merge_request_event", ["master", r"release/.+"], "master"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "merge_request_event", ["master", r"release/.+"], "some-branch"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "push", ["master", r"release/.+"], "master"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", ["master", r"release/.+"], "main"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", ["master", r"release/.+"], "some-branch"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "push", ["master", r"release/.+"], "master"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(
                ["all"], "push", ["master", r"release/.+"], "release/v1.0"
            )
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", ["master", r"release/.+"], "release_v2.0"
            )
        )

    def make_task_graph(self):
        tasks = {
            "a": Job(kind=None, label="a", attributes={}, actual_gitlab_ci_job={}),
            "b": Job(kind=None, label="b", attributes={"at-at": "yep"}, actual_gitlab_ci_job={}),
        }
        graph = Graph(nodes=set("abc"), edges=set())
        return JobGraph(tasks, graph)
