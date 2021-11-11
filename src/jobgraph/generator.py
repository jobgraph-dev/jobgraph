# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import copy
import logging
import os
from typing import AnyStr

import attr

from . import filter_jobs
from .config import DEFAULT_ROOT_DIR, GraphConfig, load_graph_config
from .graph import Graph
from .job import Job
from .jobgraph import JobGraph
from .morph import morph
from .optimize import optimize_job_graph
from .parameters import Parameters
from .transforms.base import TransformConfig, TransformSequence
from .util.python_path import find_object
from .util.verify import verifications
from .util.yaml import load_yaml

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

    def load_jobs(self, parameters, loaded_jobs, write_artifacts):
        loader = self._get_loader()
        config = copy.deepcopy(self.config)

        kind_dependencies = config.get("kind-dependencies", [])
        kind_dependencies_jobs = [
            job for job in loaded_jobs if job.kind in kind_dependencies
        ]

        inputs = loader(self.name, self.path, config, parameters, loaded_jobs)

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
            kind_dependencies_jobs,
            self.graph_config,
            write_artifacts=write_artifacts,
        )
        jobs = [
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
        return jobs

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
    generation.  The job is generated from all of the kinds defined in
    subdirectories of the generator's root directory.

    Access to the results of this generation, as well as intermediate values at
    various phases of generation, is available via properties.  This encourages
    the provision of all generation inputs at instance construction time.
    """

    # jobgraph generation is implemented as a Python generator that yields
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
        @param paramaters: parameters for this jobgraph generation, or callable
            taking a `GraphConfig` and returning parameters
        @type parameters: Union[Parameters, Callable[[GraphConfig], Parameters]]
        """
        if root_dir is None:
            root_dir = DEFAULT_ROOT_DIR
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
        The full job set: all jobs defined by any kind (a graph without edges)

        @type: JobGraph
        """
        return self._run_until("full_job_set")

    @property
    def full_job_graph(self):
        """
        The full job graph: the full job set, with edges representing
        dependencies.

        @type: JobGraph
        """
        return self._run_until("full_job_graph")

    @property
    def target_job_set(self):
        """
        The set of targetted jobs (a graph without edges)

        @type: JobGraph
        """
        return self._run_until("target_job_set")

    @property
    def target_job_graph(self):
        """
        The set of targetted jobs and all of their dependencies

        @type: JobGraph
        """
        return self._run_until("target_job_graph")

    @property
    def optimized_job_graph(self):
        """
        The set of targetted jobs and all of their dependencies; jobs that
        have been optimized out are either omitted or replaced with a Job
        instance.

        @type: JobGraph
        """
        return self._run_until("optimized_job_graph")

    @property
    def morphed_job_graph(self):
        """
        The optimized job graph, with any subsequent morphs applied. This graph
        will have the same meaning as the optimized job graph, but be in a form
        more palatable to Gitlab CI.

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

        logger.info(f"Using {parameters}")
        logger.debug(f"Dumping parameters:\n{repr(parameters)}")

        filters = parameters.get("filters", [])
        # Always add legacy target jobs method until we deprecate that API.
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

        logger.info("Generating full job set")
        all_jobs = {}
        for kind_name in kind_graph.visit_postorder():
            logger.debug(f"Loading jobs for kind {kind_name}")
            kind = kinds[kind_name]
            try:
                new_jobs = kind.load_jobs(
                    parameters,
                    list(all_jobs.values()),
                    self._write_artifacts,
                )
            except Exception:
                logger.exception(f"Error loading jobs for kind {kind_name}:")
                raise
            for job in new_jobs:
                if job.label in all_jobs:
                    raise Exception("duplicate jobs with label " + job.label)
                all_jobs[job.label] = job
            logger.info(f"Generated {len(new_jobs)} jobs for kind {kind_name}")
        full_job_set = JobGraph(all_jobs, Graph(set(all_jobs), set()))
        yield verifications("full_job_set", full_job_set, graph_config)

        logger.info("Generating full job graph")
        edges = set()
        for t in full_job_set:
            for depname, dep in t.dependencies.items():
                edges.add((t.label, dep, depname))

        full_job_graph = JobGraph(all_jobs, Graph(full_job_set.graph.nodes, edges))
        logger.info(
            "Full job graph contains %d jobs and %d dependencies"
            % (len(full_job_set.graph.nodes), len(edges))
        )
        yield verifications("full_job_graph", full_job_graph, graph_config)

        logger.info("Generating target job set")
        target_job_set = JobGraph(dict(all_jobs), Graph(set(all_jobs.keys()), set()))
        for fltr in filters:
            old_len = len(target_job_set.graph.nodes)
            target_jobs = set(fltr(target_job_set, parameters, graph_config))
            target_job_set = JobGraph(
                {l: all_jobs[l] for l in target_jobs}, Graph(target_jobs, set())
            )
            logger.info(
                "Filter %s pruned %d jobs (%d remain)"
                % (fltr.__name__, old_len - len(target_jobs), len(target_jobs))
            )

        yield verifications("target_job_set", target_job_set, graph_config)

        logger.info("Generating target job graph")
        # include all docker-image build jobs here, in case they are needed for a graph morph
        docker_image_jobs = {
            job.label
            for job in full_job_graph.jobs.values()
            if job.attributes["kind"] == "docker-image"
        }
        # include all jobs with `always_target` set
        always_target_jobs = {
            job.label
            for job in full_job_graph.jobs.values()
            if job.attributes.get("always_target")
        }
        logger.info(
            "Adding %d jobs with `always_target` attribute"
            % (len(always_target_jobs) - len(always_target_jobs & target_jobs))
        )
        target_graph = full_job_graph.graph.transitive_closure(
            target_jobs | docker_image_jobs | always_target_jobs
        )
        target_job_graph = JobGraph(
            {l: all_jobs[l] for l in target_graph.nodes}, target_graph
        )
        yield verifications("target_job_graph", target_job_graph, graph_config)

        logger.info("Generating optimized job graph")
        do_not_optimize = set(parameters.get("do_not_optimize", []))
        if not parameters.get("optimize_target_jobs", True):
            do_not_optimize = set(target_job_set.graph.nodes).union(do_not_optimize)
        optimized_job_graph = optimize_job_graph(
            target_job_graph,
            parameters,
            do_not_optimize,
            graph_config,
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
    Get all the jobs of a given kind.

    This function is designed to be called from outside of jobgraph.
    """
    # make parameters read-write
    parameters = dict(parameters)
    parameters["target-kind"] = kind
    parameters = Parameters(strict=False, **parameters)
    jgg = JobGraphGenerator(root_dir=root_dir, parameters=parameters)
    return {
        job.actual_gitlab_ci_job["metadata"]["name"]: job
        for job in jgg.full_job_set
        if job.kind == kind
    }
