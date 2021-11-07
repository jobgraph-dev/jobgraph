# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import os
import copy
import attr
from typing import AnyStr

from . import filter_jobs
from .graph import Graph
from .jobgraph import JobGraph
from .job import Job
from .optimize import optimize_task_graph
from .parameters import Parameters
from .morph import morph
from .util.python_path import find_object
from .transforms.base import TransformSequence, TransformConfig
from .util.verify import (
    verifications,
)
from .util.yaml import load_yaml
from .config import load_graph_config, GraphConfig

logger = logging.getLogger(__name__)


class KindNotFound(Exception):
    """
    Raised when trying to load kind from a directory without a kind.yml.
    """


@attr.s(frozen=True)
class Kind:

    name = attr.ib(type=AnyStr)
    path = attr.ib(type=AnyStr)
    config = attr.ib(type=dict)
    graph_config = attr.ib(type=GraphConfig)

    def _get_loader(self):
        try:
            loader = self.config["loader"]
        except KeyError:
            raise KeyError(f"{self.path!r} does not define `loader`")
        return find_object(loader)

    def load_tasks(self, parameters, loaded_tasks, write_artifacts):
        loader = self._get_loader()
        config = copy.deepcopy(self.config)

        kind_dependencies = config.get("kind-dependencies", [])
        kind_dependencies_tasks = [
            task for task in loaded_tasks if task.kind in kind_dependencies
        ]

        inputs = loader(self.name, self.path, config, parameters, loaded_tasks)

        transforms = TransformSequence()
        for xform_path in config["transforms"]:
            transform = find_object(xform_path)
            transforms.add(transform)

        # perform the transformations on the loaded inputs
        trans_config = TransformConfig(
            self.name,
            self.path,
            config,
            parameters,
            kind_dependencies_tasks,
            self.graph_config,
            write_artifacts=write_artifacts,
        )
        tasks = [
            Job(
                self.name,
                label=job_dict["label"],
                description=job_dict["description"],
                attributes=job_dict["attributes"],
                actual_gitlab_ci_job=job_dict["actual_gitlab_ci_job"],
                optimization=job_dict.get("optimization"),
                dependencies=job_dict.get("dependencies"),
            )
            for job_dict in transforms(trans_config, inputs)
        ]
        return tasks

    @classmethod
    def load(cls, root_dir, graph_config, kind_name):
        path = os.path.join(root_dir, kind_name)
        kind_yml = os.path.join(path, "kind.yml")
        if not os.path.exists(kind_yml):
            raise KindNotFound(kind_yml)

        logger.debug(f"loading kind `{kind_name}` from `{path}`")
        config = load_yaml(kind_yml)

        return cls(kind_name, path, config, graph_config)


class JobGraphGenerator:
    """
    The central controller for jobgraph.  This handles all phases of graph
    generation.  The task is generated from all of the kinds defined in
    subdirectories of the generator's root directory.

    Access to the results of this generation, as well as intermediate values at
    various phases of generation, is available via properties.  This encourages
    the provision of all generation inputs at instance construction time.
    """

    # Task-graph generation is implemented as a Python generator that yields
    # each "phase" of generation.  This allows some mach subcommands to short-
    # circuit generation of the entire graph by never completing the generator.

    def __init__(
        self,
        root_dir,
        parameters,
        write_artifacts=False,
    ):
        """
        @param root_dir: root directory, with subdirectories for each kind
        @param paramaters: parameters for this task-graph generation, or callable
            taking a `GraphConfig` and returning parameters
        @type parameters: Union[Parameters, Callable[[GraphConfig], Parameters]]
        """
        if root_dir is None:
            root_dir = "gitlab-ci/ci"
        self.root_dir = root_dir
        self._parameters = parameters
        self._write_artifacts = write_artifacts

        # start the generator
        self._run = self._run()
        self._run_results = {}

    @property
    def parameters(self):
        """
        The properties used for this graph.

        @type: Properties
        """
        return self._run_until("parameters")

    @property
    def full_job_set(self):
        """
        The full task set: all tasks defined by any kind (a graph without edges)

        @type: JobGraph
        """
        return self._run_until("full_job_set")

    @property
    def full_job_graph(self):
        """
        The full task graph: the full task set, with edges representing
        dependencies.

        @type: JobGraph
        """
        return self._run_until("full_job_graph")

    @property
    def target_job_set(self):
        """
        The set of targetted tasks (a graph without edges)

        @type: JobGraph
        """
        return self._run_until("target_job_set")

    @property
    def target_job_graph(self):
        """
        The set of targetted tasks and all of their dependencies

        @type: JobGraph
        """
        return self._run_until("target_job_graph")

    @property
    def optimized_job_graph(self):
        """
        The set of targetted tasks and all of their dependencies; tasks that
        have been optimized out are either omitted or replaced with a Task
        instance containing only a task_id.

        @type: JobGraph
        """
        return self._run_until("optimized_job_graph")

    @property
    def morphed_job_graph(self):
        """
        The optimized task graph, with any subsequent morphs applied. This graph
        will have the same meaning as the optimized task graph, but be in a form
        more palatable to TaskCluster.

        @type: JobGraph
        """
        return self._run_until("morphed_job_graph")

    @property
    def graph_config(self):
        """
        The configuration for this graph.

        @type: JobGraph
        """
        return self._run_until("graph_config")

    def _load_kinds(self, graph_config, target_kind=None):
        if target_kind:
            # docker-image is an implicit dependency that never appears in
            # kind-dependencies.
            queue = [target_kind, "docker-image"]
            seen_kinds = set()
            while queue:
                kind_name = queue.pop()
                if kind_name in seen_kinds:
                    continue
                seen_kinds.add(kind_name)
                kind = Kind.load(self.root_dir, graph_config, kind_name)
                yield kind
                queue.extend(kind.config.get("kind-dependencies", []))
        else:
            for kind_name in os.listdir(self.root_dir):
                try:
                    yield Kind.load(self.root_dir, graph_config, kind_name)
                except KindNotFound:
                    continue

    def _run(self):
        logger.info("Loading graph configuration.")
        graph_config = load_graph_config(self.root_dir)

        yield ("graph_config", graph_config)

        graph_config.register()

        if callable(self._parameters):
            parameters = self._parameters(graph_config)
        else:
            parameters = self._parameters

        logger.info("Using {}".format(parameters))
        logger.debug("Dumping parameters:\n{}".format(repr(parameters)))

        filters = parameters.get("filters", [])
        # Always add legacy target tasks method until we deprecate that API.
        if "target_jobs_method" not in filters:
            filters.insert(0, "target_jobs_method")
        filters = [filter_jobs.filter_job_functions[f] for f in filters]

        yield ("parameters", parameters)

        logger.info("Loading kinds")
        # put the kinds into a graph and sort topologically so that kinds are loaded
        # in post-order
        if parameters.get("target-kind"):
            target_kind = parameters["target-kind"]
            logger.info(
                "Limiting kinds to {target_kind} and dependencies".format(
                    target_kind=target_kind
                )
            )
        kinds = {
            kind.name: kind
            for kind in self._load_kinds(graph_config, parameters.get("target-kind"))
        }

        edges = set()
        for kind in kinds.values():
            for dep in kind.config.get("kind-dependencies", []):
                edges.add((kind.name, dep, "kind-dependency"))
        kind_graph = Graph(set(kinds), edges)

        if parameters.get("target-kind"):
            kind_graph = kind_graph.transitive_closure({target_kind, "docker-image"})

        logger.info("Generating full task set")
        all_tasks = {}
        for kind_name in kind_graph.visit_postorder():
            logger.debug(f"Loading tasks for kind {kind_name}")
            kind = kinds[kind_name]
            try:
                new_tasks = kind.load_tasks(
                    parameters,
                    list(all_tasks.values()),
                    self._write_artifacts,
                )
            except Exception:
                logger.exception(f"Error loading tasks for kind {kind_name}:")
                raise
            for task in new_tasks:
                if task.label in all_tasks:
                    raise Exception("duplicate tasks with label " + task.label)
                all_tasks[task.label] = task
            logger.info(f"Generated {len(new_tasks)} tasks for kind {kind_name}")
        full_job_set = JobGraph(all_tasks, Graph(set(all_tasks), set()))
        yield verifications("full_job_set", full_job_set, graph_config)

        logger.info("Generating full task graph")
        edges = set()
        for t in full_job_set:
            for depname, dep in t.dependencies.items():
                edges.add((t.label, dep, depname))

        full_job_graph = JobGraph(all_tasks, Graph(full_job_set.graph.nodes, edges))
        logger.info(
            "Full task graph contains %d tasks and %d dependencies"
            % (len(full_job_set.graph.nodes), len(edges))
        )
        yield verifications("full_job_graph", full_job_graph, graph_config)

        logger.info("Generating target task set")
        target_job_set = JobGraph(dict(all_tasks), Graph(set(all_tasks.keys()), set()))
        for fltr in filters:
            old_len = len(target_job_set.graph.nodes)
            target_jobs = set(fltr(target_job_set, parameters, graph_config))
            target_job_set = JobGraph(
                {l: all_tasks[l] for l in target_jobs}, Graph(target_jobs, set())
            )
            logger.info(
                "Filter %s pruned %d tasks (%d remain)"
                % (fltr.__name__, old_len - len(target_jobs), len(target_jobs))
            )

        yield verifications("target_job_set", target_job_set, graph_config)

        logger.info("Generating target task graph")
        # include all docker-image build tasks here, in case they are needed for a graph morph
        docker_image_tasks = {
            t.label
            for t in full_job_graph.jobs.values()
            if t.attributes["kind"] == "docker-image"
        }
        # include all tasks with `always_target` set
        always_target_jobs = {
            t.label
            for t in full_job_graph.jobs.values()
            if t.attributes.get("always_target")
        }
        logger.info(
            "Adding %d tasks with `always_target` attribute"
            % (len(always_target_jobs) - len(always_target_jobs & target_jobs))
        )
        target_graph = full_job_graph.graph.transitive_closure(
            target_jobs | docker_image_tasks | always_target_jobs
        )
        target_job_graph = JobGraph(
            {l: all_tasks[l] for l in target_graph.nodes}, target_graph
        )
        yield verifications("target_job_graph", target_job_graph, graph_config)

        logger.info("Generating optimized task graph")
        do_not_optimize = set(parameters.get("do_not_optimize", []))
        if not parameters.get("optimize_target_jobs", True):
            do_not_optimize = set(target_job_set.graph.nodes).union(do_not_optimize)
        optimized_job_graph = optimize_task_graph(
            target_job_graph,
            parameters,
            do_not_optimize,
        )

        yield verifications("optimized_job_graph", optimized_job_graph, graph_config)

        morphed_job_graph = morph(optimized_job_graph, parameters, graph_config)

        yield verifications("morphed_job_graph", morphed_job_graph, graph_config)

    def _run_until(self, name):
        while name not in self._run_results:
            try:
                k, v = next(self._run)
            except StopIteration:
                raise AttributeError(f"No such run result {name}")
            self._run_results[k] = v
        return self._run_results[name]


def load_jobs_for_kind(parameters, kind, root_dir=None):
    """
    Get all the tasks of a given kind.

    This function is designed to be called from outside of jobgraph.
    """
    # make parameters read-write
    parameters = dict(parameters)
    parameters["target-kind"] = kind
    parameters = Parameters(strict=False, **parameters)
    jgg = JobGraphGenerator(root_dir=root_dir, parameters=parameters)
    return {
        task.actual_gitlab_ci_job["metadata"]["name"]: task
        for task in jgg.full_job_set
        if task.kind == kind
    }
