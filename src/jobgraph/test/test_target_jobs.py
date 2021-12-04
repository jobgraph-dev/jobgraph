import unittest

from jobgraph import target_jobs
from jobgraph.graph import Graph
from jobgraph.job import Job
from jobgraph.jobgraph import JobGraph


class TestTargetJobs(unittest.TestCase):
    def default_matches_pipeline_source(self, run_on_pipeline_sources, pipeline_source):
        attributes = {
            "run_on_pipeline_sources": ["push", "web"],
            "run_on_git_branches": ["all"],
        }
        if run_on_pipeline_sources is not None:
            attributes["run_on_pipeline_sources"] = run_on_pipeline_sources

        return self.default_matches(
            attributes=attributes,
            parameters={
                "pipeline_source": pipeline_source,
                "head_ref": "main",
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
                "pipeline_source": pipeline_source,
                "head_ref": git_branch,
            },
        )

    def default_matches(self, attributes, parameters):
        method = target_jobs.get_method("default")
        graph = JobGraph(
            jobs={
                "a": Job(
                    stage="build",
                    label="a",
                    description="some build",
                    attributes=attributes,
                    actual_gitlab_ci_job={},
                ),
            },
            graph=Graph(nodes={"a"}, edges=set()),
        )
        return "a" in method(graph, parameters, {})

    def test_default_pipeline_source(self):
        self.assertFalse(self.default_matches_pipeline_source([], "push"))
        self.assertFalse(
            self.default_matches_pipeline_source([], "merge_request_event")
        )

        self.assertTrue(self.default_matches_pipeline_source(["all"], "push"))
        self.assertTrue(
            self.default_matches_pipeline_source(["all"], "merge_request_event")
        )

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
        self.assertFalse(
            self.default_matches_git_branches([], "merge_request_event", None, "master")
        )
        self.assertFalse(
            self.default_matches_git_branches(
                [], "merge_request_event", None, "some-branch"
            )
        )
        self.assertFalse(self.default_matches_git_branches([], "push", None, "master"))
        self.assertFalse(self.default_matches_git_branches([], "push", None, "main"))
        self.assertFalse(
            self.default_matches_git_branches([], "push", None, "some-branch")
        )
        self.assertFalse(self.default_matches_git_branches([], "push", None, "master"))
        self.assertFalse(
            self.default_matches_git_branches([], "push", None, "release/v1.0")
        )
        self.assertFalse(
            self.default_matches_git_branches([], "push", None, "release_v2.0")
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
            self.default_matches_git_branches(["all"], "push", ["master"], "master")
        )
        self.assertFalse(
            self.default_matches_git_branches(["all"], "push", ["master"], "main")
        )
        self.assertFalse(
            self.default_matches_git_branches(
                ["all"], "push", ["master"], "some-branch"
            )
        )
        self.assertTrue(
            self.default_matches_git_branches(["all"], "push", ["master"], "master")
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
            self.default_matches_git_branches(["all"], "push", [r"release/.+"], "main")
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
        jobs = {
            "a": Job(stage=None, label="a", attributes={}, actual_gitlab_ci_job={}),
            "b": Job(
                stage=None,
                label="b",
                attributes={"at-at": "yep"},
                actual_gitlab_ci_job={},
            ),
        }
        graph = Graph(nodes=set("abc"), edges=set())
        return JobGraph(jobs, graph)
