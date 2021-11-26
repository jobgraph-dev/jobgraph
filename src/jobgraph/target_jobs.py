# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


from jobgraph.util.attributes import (
    match_run_on_git_branches,
    match_run_on_pipeline_sources,
)

_target_task_methods = {}

_GIT_REFS_HEADS_PREFIX = "refs/heads/"


def _target_task(name):
    def wrap(func):
        _target_task_methods[name] = func
        return func

    return wrap


def get_method(method):
    """Get a target_task_method to pass to a JobGraphGenerator."""
    return _target_task_methods[method]


def filter_for_pipeline_source(task, parameters):
    run_on_pipeline_sources = set(task.attributes["run_on_pipeline_sources"])
    return match_run_on_pipeline_sources(
        parameters["pipeline_source"], run_on_pipeline_sources
    )


def filter_for_git_branch(task, parameters):
    """Filter jobs by git branch.
    If `run_on_git_branch` is not defined, then task runs on all branches"""
    # Pull requests usually have arbitrary names, let's not filter git branches on them.
    if parameters["pipeline_source"] == "merge_request_event":
        return True

    run_on_git_branches = set(task.attributes["run_on_git_branches"])
    git_branch = parameters["head_ref"]
    if git_branch.startswith(_GIT_REFS_HEADS_PREFIX):
        git_branch = git_branch[len(_GIT_REFS_HEADS_PREFIX) :]

    return match_run_on_git_branches(git_branch, run_on_git_branches)


def standard_filter(task, parameters):
    return all(
        filter_func(task, parameters)
        for filter_func in (
            filter_for_pipeline_source,
            filter_for_git_branch,
        )
    )


@_target_task("default")
def target_jobs_default(full_job_graph, parameters, graph_config):
    """Target the jobs which have indicated they should be run based on attributes."""
    return [l for l, t in full_job_graph.jobs.items() if standard_filter(t, parameters)]


@_target_task("nothing")
def target_jobs_nothing(full_job_graph, parameters, graph_config):
    """Select nothing, for DONTBUILD pushes"""
    return []
