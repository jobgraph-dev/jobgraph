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


import importlib
import logging
import os
from collections import defaultdict
from pathlib import Path

from ..graph import Graph
from ..jobgraph import JobGraph
from ..parameters import get_repo
from ..util.parameterization import resolve_task_references

logger = logging.getLogger(__name__)

TOPSRCDIR = os.path.abspath(os.path.join(__file__, "../../../"))

strategies = {}


def register_strategy(name, args=()):
    def wrap(cls):
        if name not in strategies:
            strategies[name] = cls(*args)
            if not hasattr(strategies[name], "description"):
                strategies[name].description = name
        return cls

    return wrap


def optimize_job_graph(target_job_graph, params, do_not_optimize, graph_config):
    """
    Perform task optimization, returning a JobGraph.
    """
    optimizations = _get_optimizations(target_job_graph, strategies)

    removed_jobs = remove_jobs(
        target_job_graph=target_job_graph,
        optimizations=optimizations,
        params=params,
        do_not_optimize=do_not_optimize,
    )

    return get_subgraph(
        target_job_graph,
        removed_jobs,
        graph_config,
    )


def _get_optimizations(target_job_graph, strategies):
    def optimizations(label):
        task = target_job_graph.jobs[label]
        if task.optimization:
            opt_by, arg = list(task.optimization.items())[0]
            return (opt_by, strategies[opt_by], arg)
        else:
            return ("never", strategies["never"], None)

    return optimizations


def _log_optimization(verb, opt_counts):
    if opt_counts:
        optimization_stats = ", ".join(
            f"{count} tasks by {optimization_rule}"
            for optimization_rule, count in sorted(opt_counts.items())
        )
        logger.info(f"{verb.title()} {optimization_stats} during optimization.")
    else:
        logger.info(f"No tasks {verb} during optimization")


def remove_jobs(target_job_graph, params, optimizations, do_not_optimize):
    """
    Implement the "Removing Tasks" phase, returning a set of task labels of all removed tasks.
    """
    opt_counts = defaultdict(int)
    removed = set()

    for label in target_job_graph.graph.visit_preorder():
        # if we're not allowed to optimize, that's easy..
        if label in do_not_optimize:
            continue

        # call the optimization strategy
        task = target_job_graph.jobs[label]
        opt_by, opt, arg = optimizations(label)
        if opt.should_remove_task(task, params, arg):
            removed.add(label)
            opt_counts[opt_by] += 1
            continue

    _log_optimization("removed", opt_counts)
    return removed


def get_subgraph(
    target_job_graph,
    removed_jobs,
    graph_config=None,
):
    """
    Return the subgraph of target_job_graph consisting only of
    non-optimized tasks and edges between them.
    """

    # populate task['dependencies']
    named_links_dict = target_job_graph.graph.named_links_dict()
    omit = removed_jobs
    for label, task in target_job_graph.jobs.items():
        if label in omit:
            continue
        task.task_id = "TO-BE-REMOVED"
        named_task_dependencies = {
            name: label
            for name, label in named_links_dict.get(label, {}).items()
            if label not in omit
        }

        # Add remaining soft dependencies
        if task.soft_dependencies:
            named_task_dependencies.update(
                {label: label for label in task.soft_dependencies if label not in omit}
            )

        candidate_docker_images = _get_candidate_docker_images(
            target_job_graph, named_links_dict, label, graph_config
        )

        task.actual_gitlab_ci_job = resolve_task_references(
            task.label,
            task.actual_gitlab_ci_job,
            task_id=task.task_id,
            dependencies=named_task_dependencies,
            docker_images=candidate_docker_images,
        )
        deps = task.actual_gitlab_ci_job.setdefault("needs", [])
        deps.extend(sorted(named_task_dependencies.values()))
        task.actual_gitlab_ci_job.setdefault("stage", task.stage)

    #  drop edges that are no longer entirely in the task graph
    #   (note that this omits edges to replaced tasks, but they are still in task.dependnecies)
    remaining_edges = {
        (left, right, name)
        for (left, right, name) in target_job_graph.graph.edges
        if left not in omit and right not in omit
    }
    remaining_nodes = target_job_graph.graph.nodes - omit
    remaining_tasks_by_label = {
        label: task
        for label, task in target_job_graph.jobs.items()
        if label not in omit
    }

    return JobGraph(remaining_tasks_by_label, Graph(remaining_nodes, remaining_edges))


def _get_candidate_docker_images(
    target_job_graph, named_links_dict, label, graph_config=None
):
    # TODO Remove the following line which is a workaround
    graph_config = {"docker": {}} if graph_config is None else graph_config

    docker_images = {
        name: target_job_graph.jobs[dep_label].attributes["docker_image_full_location"]
        for name, dep_label in named_links_dict.get(label, {}).items()
        if target_job_graph.jobs[dep_label].attributes.get("docker_image_full_location")
    }
    external_docker_images = graph_config["docker"].get("external-images", {})
    duplicate_image_references = set(docker_images.keys()).intersection(
        set(external_docker_images.keys())
    )
    if duplicate_image_references:
        raise ValueError(
            "Found duplicate image references between in-tree "
            f"and external ones: {duplicate_image_references}"
        )
    docker_images |= external_docker_images

    return docker_images


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


@register_strategy("always")
class Always(OptimizationStrategy):
    def should_remove_task(self, task, params, file_patterns):
        return True


@register_strategy("never")
class Never(OptimizationStrategy):
    def should_remove_task(self, task, params, file_patterns):
        return False


@register_strategy("skip-unless-changed")
class SkipUnlessChanged(OptimizationStrategy):
    def should_remove_task(self, task, params, file_patterns):
        repo = get_repo()
        repo_root = Path(repo.path)

        changed_files = repo.get_list_of_changed_files(
            params["base_rev"], params["head_rev"]
        )
        tracked_files = [
            file for pattern in file_patterns for file in repo_root.glob(pattern)
        ]

        has_any_tracked_file_changed = any(
            Path(repo_root / changed_file) == tracked_file
            for changed_file in changed_files
            for tracked_file in tracked_files
        )

        if not has_any_tracked_file_changed:
            logger.debug(
                "no files found matching a pattern in `skip-unless-changed` for "
                + task.label
            )
            return True
        return False


importlib.import_module("jobgraph.optimize.docker_registry")
