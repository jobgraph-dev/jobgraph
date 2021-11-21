# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import json
import logging
import os
import time

import yaml
from voluptuous import Optional

from jobgraph.util.python_path import find_object
from jobgraph.util.vcs import get_repository
from jobgraph.util.yaml import load_yaml

from .generator import JobGraphGenerator
from .jobgraph import JobGraph
from .parameters import Parameters
from .util.schema import Schema, validate_schema

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = "artifacts"

try_task_config_schema_v2 = Schema(
    {
        Optional("parameters"): {str: object},
    }
)


def jobgraph_decision(options, parameters=None):
    """
    Run the decision job.  This function implements `jobgraph decision`,
    and is responsible for

     * processing decision job command-line options into parameters
     * running jobgraph generation exactly the same way the other `jobgraph` commands do
     * generating a set of artifacts to memorialize the graph
     * calling Gitlab APIs to create the graph
    """

    parameters = parameters or (
        lambda graph_config: get_decision_parameters(graph_config, options)
    )

    # create a JobGraphGenerator instance
    jgg = JobGraphGenerator(
        root_dir=options.get("root"),
        parameters=parameters,
        write_artifacts=True,
    )

    # write out the parameters used to generate this graph
    write_artifact("parameters.yml", dict(**jgg.parameters))

    # write out the full graph for reference
    full_job_json = jgg.full_job_graph.to_json()
    write_artifact("full-job-graph.yml", full_job_json)

    # this is just a test to check whether the from_json() function is working
    _, _ = JobGraph.from_json(full_job_json)

    # write out the target job set to allow reproducing this as input
    write_artifact("target-jobs.yml", list(jgg.target_job_set.jobs.keys()))

    # write out the optimized job graph to describe what will actually happen
    write_artifact("optimized-job-graph.yml", jgg.optimized_job_graph.to_json())
    write_artifact(
        "generated-gitlab-ci.yml", jgg.optimized_job_graph.to_gitlab_ci_jobs()
    )


def get_decision_parameters(graph_config, options):
    """
    Load parameters from the command-line options for 'jobgraph decision'.

    """
    parameters = {
        n: options[n]
        for n in [
            "base_repository",
            "base_rev",
            "head_repository",
            "head_rev",
            "head_ref",
            "head_ref_protection",
            "head_tag",
            "owner",
            "target_jobs_method",
            "pipeline_source",
        ]
        if n in options
    }

    repo = get_repository(os.getcwd())
    commit_message = repo.get_commit_message()

    # Define default filter list, as most configurations shouldn't need
    # custom filters.
    parameters["filters"] = [
        "target_jobs_method",
    ]
    parameters["optimize_target_jobs"] = True
    parameters["do_not_optimize"] = []

    # owner must be an email, but sometimes (e.g., for ffxbld) it is not, in which
    # case, fake it
    if "@" not in parameters["owner"]:
        parameters["owner"] += "@noreply.mozilla.org"

    parameters["build_date"] = int(time.time())
    parameters["target_jobs_method"] = options.get("target_jobs_method", "default")

    # ..but can be overridden by the commit message: if it contains the special
    # string "DONTBUILD" and this is an on-push decision job, then use the
    # special 'nothing' target job method.
    if "DONTBUILD" in commit_message and options["pipeline_source"] == "push":
        parameters["target_jobs_method"] = "nothing"

    if options.get("optimize_target_jobs") is not None:
        parameters["optimize_target_jobs"] = options["optimize_target_jobs"]

    if "decision_parameters" in graph_config["jobgraph"]:
        find_object(graph_config["jobgraph"]["decision_parameters"])(
            graph_config, parameters
        )

    if options.get("try_task_config_file"):
        task_config_file = os.path.abspath(options.get("try_task_config_file"))
    else:
        # if try_task_config.json is present, load it
        task_config_file = os.path.join(os.getcwd(), "try_task_config.json")

    # load try settings
    if options["pipeline_source"] == "merge_request_event":
        set_try_config(parameters, task_config_file)

    result = Parameters(**parameters)
    result.check()
    return result


def set_try_config(parameters, task_config_file):
    if os.path.isfile(task_config_file):
        logger.info(f"using try tasks from {task_config_file}")
        with open(task_config_file) as fh:
            task_config = json.load(fh)
        task_config_version = task_config.pop("version")
        if task_config_version == 2:
            validate_schema(
                try_task_config_schema_v2,
                task_config,
                "Invalid v2 `try_task_config.json`.",
            )
            parameters.update(task_config["parameters"])
            return
        else:
            raise Exception(
                f"Unknown `try_task_config.json` version: {task_config_version}"
            )


def write_artifact(filename, data):
    logger.info(f"writing artifact file `{filename}`")
    if not os.path.isdir(ARTIFACTS_DIR):
        os.mkdir(ARTIFACTS_DIR)
    path = os.path.join(ARTIFACTS_DIR, filename)
    if filename.endswith(".yml"):
        with open(path, "w") as f:
            yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)
    elif filename.endswith(".json"):
        with open(path, "w") as f:
            json.dump(data, f, sort_keys=True, indent=2, separators=(",", ": "))
    elif filename.endswith(".gz"):
        import gzip

        with gzip.open(path, "wb") as f:
            f.write(json.dumps(data))
    else:
        raise TypeError(f"Don't know how to write to {filename}")


def read_artifact(filename):
    path = os.path.join(ARTIFACTS_DIR, filename)
    if filename.endswith(".yml"):
        return load_yaml(path, filename)
    elif filename.endswith(".json"):
        with open(path) as f:
            return json.load(f)
    elif filename.endswith(".gz"):
        import gzip

        with gzip.open(path, "rb") as f:
            return json.load(f)
    else:
        raise TypeError(f"Don't know how to read {filename}")


def rename_artifact(src, dest):
    os.rename(os.path.join(ARTIFACTS_DIR, src), os.path.join(ARTIFACTS_DIR, dest))
