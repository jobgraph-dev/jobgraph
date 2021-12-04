import unittest
from functools import partial

from slugid import nice as slugid

from jobgraph import graph, optimize
from jobgraph.job import Job
from jobgraph.jobgraph import JobGraph


class Remove(optimize.OptimizationStrategy):
    def should_remove_job(self, task, params, arg):
        return True


class TestOptimize(unittest.TestCase):

    strategies = {
        "never": optimize.OptimizationStrategy(),
        "remove": Remove(),
    }

    def make_task(
        self,
        label,
        optimization=None,
        task_def=None,
        optimized=None,
        upstream_dependencies=None,
    ):
        task_def = task_def or {
            "image": "some-image",
            "script": "some-script",
            "tags": ["some_runner_tag"],
        }
        task = Job(
            stage="test",
            label=label,
            description="some test description",
            attributes={},
            actual_gitlab_ci_job=task_def,
        )
        task.optimization = optimization
        if upstream_dependencies is not None:
            task.actual_gitlab_ci_job["needs"] = sorted(upstream_dependencies)
            task.actual_gitlab_ci_job["stage"] = "test"
        return task

    def make_graph(self, *jobs_and_edges):
        jobs = {j.label: j for j in jobs_and_edges if isinstance(j, Job)}
        edges = {e for e in jobs_and_edges if not isinstance(e, Job)}
        return JobGraph(jobs, graph.Graph(set(jobs), edges))

    def make_opt_graph(self, *jobs_and_edges):
        jobs = {j.label: j for j in jobs_and_edges if isinstance(j, Job)}
        edges = {e for e in jobs_and_edges if not isinstance(e, Job)}
        return JobGraph(jobs, graph.Graph(set(jobs), edges))

    def make_triangle(self, **opts):
        """
        Make a "triangle" graph like this:

          t1 <-------- t3
           `---- t2 --'
        """
        return self.make_graph(
            self.make_task("t1", opts.get("t1")),
            self.make_task("t2", opts.get("t2")),
            self.make_task("t3", opts.get("t3")),
            ("t3", "t2", "dep"),
            ("t3", "t1", "dep2"),
            ("t2", "t1", "dep"),
        )

    def assert_remove_jobs(self, graph, exp_removed, do_not_optimize=set()):
        got_removed = optimize.remove_jobs(
            target_job_graph=graph,
            optimizations=optimize._get_optimizations(graph, self.strategies),
            params={},
            do_not_optimize=do_not_optimize,
        )
        self.assertEqual(got_removed, exp_removed)

    def test_remove_jobs_never(self):
        "A graph full of optimization=never has nothing removed"
        graph = self.make_triangle()
        self.assert_remove_jobs(graph, set())

    def test_remove_jobs_all(self):
        "A graph full of optimization=remove has removed everything"
        graph = self.make_triangle(
            t1={"remove": None}, t2={"remove": None}, t3={"remove": None}
        )
        self.assert_remove_jobs(graph, {"t1", "t2", "t3"})

    def test_remove_jobs_blocked(self):
        "Removable jobs that depend on non-removable jobs are not removed"
        graph = self.make_triangle(t1={}, t3={"remove": None})
        self.assert_remove_jobs(graph, set())

    def test_remove_jobs_do_not_optimize(self):
        "Removable jobs that are marked do_not_optimize are not removed"
        graph = self.make_triangle(
            t1={"remove": None},
            t2={"remove": None},  # but do_not_optimize
            t3={"remove": None},
        )
        self.assert_remove_jobs(graph, {"t1"}, do_not_optimize={"t2"})

    def assert_subgraph(
        self,
        graph,
        removed_jobs,
        exp_subgraph,
    ):
        self.maxDiff = None
        optimize.slugid = partial(next, (f"tid{i}" for i in range(1, 10)))
        try:
            got_subgraph = optimize.get_subgraph(
                graph,
                removed_jobs,
            )
        finally:
            optimize.slugid = slugid
        self.assertEqual(got_subgraph.graph, exp_subgraph.graph)
        self.assertEqual(got_subgraph.jobs, exp_subgraph.jobs)

    def test_get_subgraph_no_change(self):
        "get_subgraph returns a similarly-shaped subgraph when nothing is removed"
        graph = self.make_triangle()
        self.assert_subgraph(
            graph,
            set(),
            self.make_opt_graph(
                self.make_task("t1", upstream_dependencies={}),
                self.make_task("t2", upstream_dependencies={"t1"}),
                self.make_task("t3", upstream_dependencies={"t1", "t2"}),
                ("t3", "t2", "dep"),
                ("t3", "t1", "dep2"),
                ("t2", "t1", "dep"),
            ),
        )

    def test_get_subgraph_removed(self):
        "get_subgraph returns a smaller subgraph when jobs are removed"
        graph = self.make_triangle()
        self.assert_subgraph(
            graph,
            {"t2", "t3"},
            self.make_opt_graph(self.make_task("t1", upstream_dependencies={})),
        )
