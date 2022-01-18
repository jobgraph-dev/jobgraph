"""
The objective of optimization is to remove as many jobs from the graph as
possible, as efficiently as possible, thereby delivering useful results as
quickly as possible.  For example, ideally if only a test script is modified in
a push, then the resulting graph contains only the corresponding test suite
job.
"""


import importlib
import logging
import os
from collections import defaultdict
from pathlib import Path
from subprocess import CalledProcessError

from yaml import safe_load

from ..graph import Graph
from ..jobgraph import JobGraph
from ..parameters import get_repo
from ..util.parameterization import resolve_docker_image_references
from ..util.schema import gitlab_ci_job_output, validate_schema

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
    Perform job optimization, returning a JobGraph.
    """
    changed_external_docker_images = _get_changed_external_docker_images(
        params, graph_config
    )
    _remove_optimization_if_any_external_docker_image_has_changed(
        target_job_graph, changed_external_docker_images
    )

    optimizations = _get_optimizations(target_job_graph, strategies)

    removed_jobs = remove_jobs(
        target_job_graph=target_job_graph,
        optimizations=optimizations,
        params=params,
        do_not_optimize=do_not_optimize,
        graph_config=graph_config,
    )

    return get_subgraph(
        target_job_graph,
        removed_jobs,
        graph_config,
    )


def _get_changed_external_docker_images(params, graph_config):
    repo = get_repo()
    config_file_relative_path = os.path.relpath(
        graph_config.config_yml, graph_config.vcs_root
    )

    try:
        config_yml_at_base_rev = repo.get_file_at_given_revision(
            params["base_rev"], config_file_relative_path
        )
        external_docker_images_at_base_rev = (
            safe_load(config_yml_at_base_rev)
            .get("docker", {})
            .get("external_images", {})
        )
    except CalledProcessError:
        # File may not exist at base_rev. This may occur when performing a
        # migration to jobgraph
        #
        # TODO: narrow down this error to avoid hiding other errors
        external_docker_images_at_base_rev = {}

    external_docker_images = graph_config["docker"].get("external_images", {})

    return {
        image_reference
        for image_reference, image_full_location in external_docker_images.items()
        if image_full_location not in external_docker_images_at_base_rev.values()
    }


def _remove_optimization_if_any_external_docker_image_has_changed(
    target_job_graph, changed_external_docker_images
):
    for label in target_job_graph.graph.visit_preorder():
        job = target_job_graph.jobs[label]
        image_reference = job.actual_gitlab_ci_job["image"][
            "docker_image_reference"
        ].strip("<>")
        service_image_references = [
            service.get("docker_image_reference", "").strip("<>")
            for service in job.actual_gitlab_ci_job.get("services", {})
            if service.get("docker_image_reference", "")
        ]
        all_image_references = [image_reference] + service_image_references
        if any(
            image_reference in changed_external_docker_images
            for image_reference in all_image_references
        ):
            logger.debug(
                f'Cannot optimize "{label}", one or many of its external '
                "docker images have changed."
            )
            job.optimization = {}


def _get_optimizations(target_job_graph, strategies):
    def optimizations(label):
        job = target_job_graph.jobs[label]
        if job.optimization:
            opt_by, arg = list(job.optimization.items())[0]
            return (opt_by, strategies[opt_by], arg)
        else:
            return ("never", strategies["never"], None)

    return optimizations


def _log_optimization(verb, opt_counts):
    if opt_counts:
        optimization_stats = ", ".join(
            f"{count} jobs by {optimization_rule}"
            for optimization_rule, count in sorted(opt_counts.items())
        )
        logger.info(f"{verb.title()} {optimization_stats} during optimization.")
    else:
        logger.info(f"No jobs {verb} during optimization")


def remove_jobs(target_job_graph, params, optimizations, do_not_optimize, graph_config):
    """
    Implement the "Removing Jobs" phase, returning a set of job labels of all
    removed jobs.
    """
    opt_counts = defaultdict(int)
    removed = set()

    for label in target_job_graph.graph.visit_postorder():
        # if we're not allowed to optimize, that's easy..
        if label in do_not_optimize:
            continue

        # Do not optimize job if one of its upstreams deps wasn't optimized
        # away. This usually means something upstream is new and we have to
        # run the job anyway
        job = target_job_graph.jobs[label]
        named_links_dict = target_job_graph.graph.named_links_dict()
        named_job_dependencies = {
            upstream_dep_reference: upstream_dep_label
            for upstream_dep_reference, upstream_dep_label in named_links_dict.get(
                label, {}
            ).items()
            if upstream_dep_label not in removed
        }
        if named_job_dependencies:
            job.optimization = {}

        # call the optimization strategy
        opt_by, opt, arg = optimizations(label)
        if opt.should_remove_job(job, params, graph_config, arg):
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
    non-optimized jobs and edges between them.
    """

    # populate job['upstream_dependencies']
    named_links_dict = target_job_graph.graph.named_links_dict()
    omit = removed_jobs
    for label, job in target_job_graph.jobs.items():
        if label in omit:
            continue
        named_job_dependencies = {
            name: label
            for name, label in named_links_dict.get(label, {}).items()
            if label not in omit
        }

        candidate_docker_images = _get_candidate_docker_images(
            target_job_graph, named_links_dict, label, graph_config
        )

        job.actual_gitlab_ci_job = resolve_docker_image_references(
            job.label,
            job.actual_gitlab_ci_job,
            docker_images=candidate_docker_images,
        )
        unique_dependencies = set(named_job_dependencies.values())
        needs = job.actual_gitlab_ci_job.setdefault("needs", [])
        needs.extend(sorted(list(unique_dependencies)))
        job.actual_gitlab_ci_job.setdefault("stage", job.stage)
        validate_schema(
            gitlab_ci_job_output,
            job.actual_gitlab_ci_job,
            f"In job {job.label}:",
        )

    #  drop edges that are no longer entirely in the job graph
    #   (note that this omits edges to replaced jobs, but they are still
    #    in job.dependencies)
    remaining_edges = {
        (left, right, name)
        for (left, right, name) in target_job_graph.graph.edges
        if left not in omit and right not in omit
    }
    remaining_nodes = target_job_graph.graph.nodes - omit
    remaining_jobs_by_label = {
        label: job for label, job in target_job_graph.jobs.items() if label not in omit
    }

    return JobGraph(remaining_jobs_by_label, Graph(remaining_nodes, remaining_edges))


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
    external_docker_images = graph_config["docker"].get("external_images", {})
    duplicate_image_references = set(docker_images.keys()).intersection(
        set(external_docker_images.keys())
    )
    if duplicate_image_references:
        raise ValueError(
            "Found duplicate image references between in_tree "
            f"and external ones: {duplicate_image_references}"
        )
    docker_images |= external_docker_images

    return docker_images


class OptimizationStrategy:
    def should_remove_job(self, job, params, graph_config, arg):
        """Determine whether to optimize this job by removing it.  Returns
        True to remove."""
        return False


@register_strategy("always")
class Always(OptimizationStrategy):
    def should_remove_job(self, job, params, graph_config, file_patterns):
        return True


@register_strategy("never")
class Never(OptimizationStrategy):
    def should_remove_job(self, job, params, graph_config, file_patterns):
        return False


@register_strategy("skip_unless_changed")
class SkipUnlessChanged(OptimizationStrategy):
    def should_remove_job(self, job, params, graph_config, file_patterns):
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
                "no files found matching a pattern in `skip_unless_changed` for "
                + job.label
            )
            return True
        return False


importlib.import_module("jobgraph.optimize.docker_registry")
importlib.import_module("jobgraph.optimize.cache")
