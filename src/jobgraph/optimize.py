# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
The objective of optimization is to remove as many tasks from the graph as
possible, as efficiently as possible, thereby delivering useful results as
quickly as possible.  For example, ideally if only a test script is modified in
a push, then the resulting graph contains only the corresponding test suite
task.

See ``taskcluster/docs/optimization.rst`` for more information.
"""


import logging
import os
from collections import defaultdict

from slugid import nice as slugid

from .graph import Graph
from . import files_changed
from .jobgraph import JobGraph
from .util.parameterization import resolve_task_references

logger = logging.getLogger(__name__)

TOPSRCDIR = os.path.abspath(os.path.join(__file__, "../../../"))


def optimize_task_graph(
    target_task_graph,
    params,
    do_not_optimize,
    decision_task_id,
    existing_tasks=None,
    strategies=None,
):
    """
    Perform task optimization, returning a JobGraph.
    """
    if not existing_tasks:
        existing_tasks = {}

    # instantiate the strategies for this optimization process
    if not strategies:
        strategies = _make_default_strategies()

    optimizations = _get_optimizations(target_task_graph, strategies)

    removed_tasks = remove_tasks(
        target_task_graph=target_task_graph,
        optimizations=optimizations,
        params=params,
        do_not_optimize=do_not_optimize,
    )

    replaced_tasks = replace_tasks(
        target_task_graph=target_task_graph,
        optimizations=optimizations,
        params=params,
        do_not_optimize=do_not_optimize,
        existing_tasks=existing_tasks,
        removed_tasks=removed_tasks,
    )

    return get_subgraph(
        target_task_graph,
        removed_tasks,
        replaced_tasks,
        decision_task_id,
    )


def _make_default_strategies():
    return {
        "never": OptimizationStrategy(),  # "never" is the default behavior
        "skip-unless-changed": SkipUnlessChanged(),
    }


def _get_optimizations(target_task_graph, strategies):
    def optimizations(label):
        task = target_task_graph.jobs[label]
        if task.optimization:
            opt_by, arg = list(task.optimization.items())[0]
            return (opt_by, strategies[opt_by], arg)
        else:
            return ("never", strategies["never"], None)

    return optimizations


def _log_optimization(verb, opt_counts):
    if opt_counts:
        logger.info(
            "{} {} during optimization.".format(
                verb.title(),
                ", ".join(f"{c} tasks by {b}" for b, c in sorted(opt_counts.items())),
            )
        )
    else:
        logger.info(f"No tasks {verb} during optimization")


def remove_tasks(target_task_graph, params, optimizations, do_not_optimize):
    """
    Implement the "Removing Tasks" phase, returning a set of task labels of all removed tasks.
    """
    opt_counts = defaultdict(int)
    removed = set()
    reverse_links_dict = target_task_graph.graph.reverse_links_dict()

    for label in target_task_graph.graph.visit_preorder():
        # if we're not allowed to optimize, that's easy..
        if label in do_not_optimize:
            continue

        # if there are remaining tasks depending on this one, do not remove..
        if any(l not in removed for l in reverse_links_dict[label]):
            continue

        # call the optimization strategy
        task = target_task_graph.jobs[label]
        opt_by, opt, arg = optimizations(label)
        if opt.should_remove_task(task, params, arg):
            removed.add(label)
            opt_counts[opt_by] += 1
            continue

    _log_optimization("removed", opt_counts)
    return removed


def replace_tasks(
    target_task_graph,
    params,
    optimizations,
    do_not_optimize,
    removed_tasks,
    existing_tasks,
):
    """
    Implement the "Replacing Tasks" phase, returning a set of task labels of
    all replaced tasks.
    """
    opt_counts = defaultdict(int)
    replaced = set()
    links_dict = target_task_graph.graph.links_dict()

    for label in target_task_graph.graph.visit_postorder():
        # if we're not allowed to optimize, that's easy..
        if label in do_not_optimize:
            continue

        # if this task depends on un-replaced, un-removed tasks, do not replace
        if any(l not in replaced and l not in removed_tasks for l in links_dict[label]):
            continue

        # if the task already exists, that's an easy replacement
        repl = existing_tasks.get(label)
        if repl:
            replaced.add(label)
            opt_counts["existing_tasks"] += 1
            continue

        # call the optimization strategy
        task = target_task_graph.jobs[label]
        opt_by, opt, arg = optimizations(label)
        repl = opt.should_replace_task(task, params, arg)
        if repl:
            if repl is True:
                # True means remove this task; get_subgraph will catch any
                # problems with removed tasks being depended on
                removed_tasks.add(label)
            else:
                replaced.add(label)
            opt_counts[opt_by] += 1
            continue

    _log_optimization("replaced", opt_counts)
    return replaced


def get_subgraph(
    target_task_graph,
    removed_tasks,
    replaced_tasks,
    decision_task_id,
):
    """
    Return the subgraph of target_task_graph consisting only of
    non-optimized tasks and edges between them.
    """

    # check for any dependency edges from included to removed tasks
    bad_edges = [
        (l, r, n)
        for l, r, n in target_task_graph.graph.edges
        if l not in removed_tasks and r in removed_tasks
    ]
    if bad_edges:
        probs = ", ".join(
            f"{l} depends on {r} as {n} but it has been removed"
            for l, r, n in bad_edges
        )
        raise Exception("Optimization error: " + probs)

    # populate task['dependencies']
    named_links_dict = target_task_graph.graph.named_links_dict()
    omit = removed_tasks | replaced_tasks
    for label, task in target_task_graph.jobs.items():
        if label in omit:
            continue
        task.task_id = "TO-BE-REMOVED"
        named_task_dependencies = {
            name: label
            for name, label in named_links_dict.get(label, {}).items()
        }

        # Add remaining soft dependencies
        if task.soft_dependencies:
            named_task_dependencies.update(
                {
                    label: label
                    for label in task.soft_dependencies
                    if label not in omit
                }
            )

        task.actual_gitlab_ci_job = resolve_task_references(
            task.label,
            task.actual_gitlab_ci_job,
            task_id=task.task_id,
            decision_task_id=decision_task_id,
            dependencies=named_task_dependencies,
        )
        deps = task.actual_gitlab_ci_job.setdefault("needs", [])
        deps.extend(sorted(named_task_dependencies.values()))

    #  drop edges that are no longer entirely in the task graph
    #   (note that this omits edges to replaced tasks, but they are still in task.dependnecies)
    remaining_edges = {
        (left, right, name)
        for (left, right, name) in target_task_graph.graph.edges
        if left not in omit and right not in omit
    }
    remaining_nodes = target_task_graph.graph.nodes - omit
    remaining_tasks_by_label = {
        label: task
        for label, task in target_task_graph.jobs.items()
        if label not in omit
    }

    return JobGraph(remaining_tasks_by_label, Graph(remaining_nodes, remaining_edges))


class OptimizationStrategy:
    def should_remove_task(self, task, params, arg):
        """Determine whether to optimize this task by removing it.  Returns
        True to remove."""
        return False

    def should_replace_task(self, task, params, arg):
        """Determine whether to optimize this task by replacing it.  Returns a
        taskId to replace this task, True to replace with nothing, or False to
        keep the task."""
        return False


class Either(OptimizationStrategy):
    """Given one or more optimization strategies, remove a task if any of them
    says to, and replace with a task if any finds a replacement (preferring the
    earliest).  By default, each substrategy gets the same arg, but split_args
    can return a list of args for each strategy, if desired."""

    def __init__(self, *substrategies, **kwargs):
        self.substrategies = substrategies
        self.split_args = kwargs.pop("split_args", None)
        if not self.split_args:
            self.split_args = lambda arg: [arg] * len(substrategies)
        if kwargs:
            raise TypeError("unexpected keyword args")

    def _for_substrategies(self, arg, fn):
        for sub, arg in zip(self.substrategies, self.split_args(arg)):
            rv = fn(sub, arg)
            if rv:
                return rv
        return False

    def should_remove_task(self, task, params, arg):
        return self._for_substrategies(
            arg, lambda sub, arg: sub.should_remove_task(task, params, arg)
        )

    def should_replace_task(self, task, params, arg):
        return self._for_substrategies(
            arg, lambda sub, arg: sub.should_replace_task(task, params, arg)
        )


class SkipUnlessChanged(OptimizationStrategy):
    def should_remove_task(self, task, params, file_patterns):
        if params.get("repository_type") != "hg":
            raise RuntimeError(
                "SkipUnlessChanged optimization only works with mercurial repositories"
            )

        changed = files_changed.check(params, file_patterns)
        if not changed:
            logger.debug(
                'no files found matching a pattern in `skip-unless-changed` for "{}"'.format(
                    task.label
                )
            )
            return True
        return False
