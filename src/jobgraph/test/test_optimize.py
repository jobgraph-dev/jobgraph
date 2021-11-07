# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import unittest
from functools import partial

from slugid import nice as slugid

from jobgraph import optimize
from jobgraph.jobgraph import JobGraph
from jobgraph import graph
from jobgraph.job import Job


class Remove(optimize.OptimizationStrategy):
    def should_remove_task(self, task, params, arg):
        return True


class Replace(optimize.OptimizationStrategy):
    def should_replace_task(self, task, params, taskid):
        return taskid


class TestOptimize(unittest.TestCase):

    strategies = {
        "never": optimize.OptimizationStrategy(),
        "remove": Remove(),
        "replace": Replace(),
    }

    def make_task(
        self,
        label,
        optimization=None,
        task_def=None,
        optimized=None,
        task_id=None,
        dependencies=None,
    ):
        task_def = task_def or {"sample": "task-def"}
        task = Job(
            kind="test",
            label=label,
            description="some test description",
            attributes={},
            actual_gitlab_ci_job=task_def,
        )
        task.optimization = optimization
        task.task_id = task_id
        if dependencies is not None:
            task.actual_gitlab_ci_job["needs"] = sorted(dependencies)
            task.actual_gitlab_ci_job["stage"] = "test"
        return task

    def make_graph(self, *tasks_and_edges):
        tasks = {t.label: t for t in tasks_and_edges if isinstance(t, Job)}
        edges = {e for e in tasks_and_edges if not isinstance(e, Job)}
        return JobGraph(tasks, graph.Graph(set(tasks), edges))

    def make_opt_graph(self, *tasks_and_edges):
        tasks = {t.label: t for t in tasks_and_edges if isinstance(t, Job)}
        edges = {e for e in tasks_and_edges if not isinstance(e, Job)}
        return JobGraph(tasks, graph.Graph(set(tasks), edges))

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
        "A graph full of optimization=remove has removes everything"
        graph = self.make_triangle(
            t1={"remove": None}, t2={"remove": None}, t3={"remove": None}
        )
        self.assert_remove_jobs(graph, {"t1", "t2", "t3"})

    def test_remove_jobs_blocked(self):
        "Removable tasks that are depended on by non-removable tasks are not removed"
        graph = self.make_triangle(t1={"remove": None}, t3={"remove": None})
        self.assert_remove_jobs(graph, {"t1", "t3"})

    def test_remove_jobs_do_not_optimize(self):
        "Removable tasks that are marked do_not_optimize are not removed"
        graph = self.make_triangle(
            t1={"remove": None},
            t2={"remove": None},  # but do_not_optimize
            t3={"remove": None},
        )
        self.assert_remove_jobs(graph, {"t1", "t3"}, do_not_optimize={"t2"})

    def assert_replace_tasks(
        self,
        graph,
        exp_replaced,
        exp_removed=set(),
        do_not_optimize=None,
        removed_tasks=None,
        existing_tasks=None,
    ):
        do_not_optimize = do_not_optimize or set()
        removed_tasks = removed_tasks or set()
        existing_tasks = existing_tasks or {}

        got_replaced = optimize.replace_tasks(
            target_job_graph=graph,
            optimizations=optimize._get_optimizations(graph, self.strategies),
            params={},
            do_not_optimize=do_not_optimize,
            removed_tasks=removed_tasks,
            existing_tasks=existing_tasks,
        )
        self.assertEqual(got_replaced, exp_replaced)
        self.assertEqual(removed_tasks, exp_removed)

    def test_replace_tasks_never(self):
        "No tasks are replaced when strategy is 'never'"
        graph = self.make_triangle()
        self.assert_replace_tasks(graph, set())

    def test_replace_tasks_all(self):
        "All replacable tasks are replaced when strategy is 'replace'"
        graph = self.make_triangle(
            t1={"replace": "e1"}, t2={"replace": "e2"}, t3={"replace": "e3"}
        )
        self.assert_replace_tasks(
            graph,
            exp_replaced={"t1", "t2", "t3"},
        )

    def test_replace_tasks_blocked(self):
        "A task cannot be replaced if it depends on one that was not replaced"
        graph = self.make_triangle(t1={"replace": "e1"}, t3={"replace": "e3"})
        self.assert_replace_tasks(graph, exp_replaced={"t1"})

    def test_replace_tasks_do_not_optimize(self):
        "A task cannot be replaced if it depends on one that was not replaced"
        graph = self.make_triangle(
            t1={"replace": "e1"},
            t2={"replace": "xxx"},  # but do_not_optimize
            t3={"replace": "e3"},
        )
        self.assert_replace_tasks(
            graph,
            exp_replaced={"t1"},
            do_not_optimize={"t2"},
        )

    def test_replace_tasks_removed(self):
        "A task can be replaced with nothing"
        graph = self.make_triangle(
            t1={"replace": "e1"}, t2={"replace": True}, t3={"replace": True}
        )
        self.assert_replace_tasks(
            graph,
            exp_replaced={"t1"},
            exp_removed={"t2", "t3"},
        )

    def assert_subgraph(
        self,
        graph,
        removed_tasks,
        replaced_tasks,
        exp_subgraph,
    ):
        self.maxDiff = None
        optimize.slugid = partial(next, ("tid%d" % i for i in range(1, 10)))
        try:
            got_subgraph = optimize.get_subgraph(
                graph,
                removed_tasks,
                replaced_tasks,
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
            set(),
            self.make_opt_graph(
                self.make_task("t1", task_id="TO-BE-REMOVED", dependencies={}),
                self.make_task("t2", task_id="TO-BE-REMOVED", dependencies={"t1"}),
                self.make_task(
                    "t3", task_id="TO-BE-REMOVED", dependencies={"t1", "t2"}
                ),
                ("t3", "t2", "dep"),
                ("t3", "t1", "dep2"),
                ("t2", "t1", "dep"),
            ),
        )

    def test_get_subgraph_removed(self):
        "get_subgraph returns a smaller subgraph when tasks are removed"
        graph = self.make_triangle()
        self.assert_subgraph(
            graph,
            {"t2", "t3"},
            set(),
            self.make_opt_graph(
                self.make_task("t1", task_id="TO-BE-REMOVED", dependencies={})
            ),
        )
