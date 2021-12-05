from jobgraph.util.attributes import (
    match_run_on_git_branches,
    match_run_on_pipeline_sources,
)

_target_jobs_methods = {}

_GIT_REFS_HEADS_PREFIX = "refs/heads/"


def target_jobs(name):
    def wrap(func):
        _target_jobs_methods[name] = func
        return func

    return wrap


def get_method(method):
    """Get a target_job_method to pass to a JobGraphGenerator."""
    return _target_jobs_methods[method]


def filter_for_pipeline_source(job, parameters):
    run_on_pipeline_sources = set(job.attributes["run_on_pipeline_sources"])
    return match_run_on_pipeline_sources(
        parameters["pipeline_source"], run_on_pipeline_sources
    )


def filter_for_git_branch(job, parameters):
    """Filter jobs by git branch.
    If `run_on_git_branch` is not defined, then job runs on all branches"""
    # Pull requests usually have arbitrary names, let's not filter git branches on them.
    if parameters["pipeline_source"] == "merge_request_event":
        return True

    run_on_git_branches = set(job.attributes["run_on_git_branches"])
    git_branch = parameters["head_ref"]
    if git_branch.startswith(_GIT_REFS_HEADS_PREFIX):
        git_branch = git_branch[len(_GIT_REFS_HEADS_PREFIX) :]

    return match_run_on_git_branches(git_branch, run_on_git_branches)


def filter_out_schedules(task, parameters):
    """
    Filter out jobs that run within a schedule.
    """
    return not task.attributes.get("schedules")


def standard_filter(job, parameters):
    return all(
        filter_func(job, parameters)
        for filter_func in (
            filter_for_pipeline_source,
            filter_for_git_branch,
            filter_out_schedules,
        )
    )


@target_jobs("default")
def target_jobs_default(full_job_graph, parameters, graph_config):
    """Target the jobs which have indicated they should be run based on attributes."""
    return [
        label
        for label, t in full_job_graph.jobs.items()
        if standard_filter(t, parameters)
    ]


@target_jobs("nothing")
def target_jobs_nothing(full_job_graph, parameters, graph_config):
    """Select nothing, for DONTBUILD pushes"""
    return []


@target_jobs("jobgraph_updates")
def target_jobs_jobgraph_updates(full_job_graph, parameters, graph_config):
    """Target the jobs which have indicated they should be run based on attributes."""

    def filter(job, parameters):
        return job.attributes.get("schedules", {}).get("jobgraph_updates", False)

    return [label for label, t in full_job_graph.jobs.items() if filter(t, parameters)]
