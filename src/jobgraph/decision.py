# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import os
import json
import logging


import time
import yaml

from .create import create_tasks
from .generator import JobGraphGenerator
from .parameters import Parameters
from .jobgraph import JobGraph
from jobgraph.util.python_path import find_object
from jobgraph.util.vcs import get_repository
from .util.schema import validate_schema, Schema
from jobgraph.util.yaml import load_yaml
from voluptuous import Optional


logger = logging.getLogger(__name__)

ARTIFACTS_DIR = "artifacts"

# For each project, this gives a set of parameters specific to the project.
# See `taskcluster/docs/parameters.rst` for information on parameters.
PER_PROJECT_PARAMETERS = {
    # the default parameters are used for projects that do not match above.
    "default": {
        "target_tasks_method": "default",
    }
}


try_task_config_schema_v2 = Schema(
    {
        Optional("parameters"): {str: object},
    }
)


def taskgraph_decision(options, parameters=None):
    """
    Run the decision task.  This function implements `mach taskgraph decision`,
    and is responsible for

     * processing decision task command-line options into parameters
     * running task-graph generation exactly the same way the other `mach
       taskgraph` commands do
     * generating a set of artifacts to memorialize the graph
     * calling TaskCluster APIs to create the graph
    """

    parameters = parameters or (
        lambda graph_config: get_decision_parameters(graph_config, options)
    )

    decision_task_id = os.environ["TASK_ID"]

    # create a TaskGraphGenerator instance
    jgg = JobGraphGenerator(
        root_dir=options.get("root"),
        parameters=parameters,
        decision_task_id=decision_task_id,
        write_artifacts=True,
    )

    # write out the parameters used to generate this graph
    write_artifact("parameters.yml", dict(**jgg.parameters))

    # write out the full graph for reference
    full_task_json = jgg.full_task_graph.to_json()
    write_artifact("full-task-graph.json", full_task_json)

    # this is just a test to check whether the from_json() function is working
    _, _ = JobGraph.from_json(full_task_json)

    # write out the target task set to allow reproducing this as input
    write_artifact("target-tasks.json", list(jgg.target_task_set.tasks.keys()))

    # write out the optimized task graph to describe what will actually happen,
    # and the map of labels to taskids
    write_artifact("task-graph.json", jgg.morphed_task_graph.to_json())
    write_artifact("label-to-taskid.json", jgg.label_to_taskid)

    # actually create the graph
    create_tasks(
        jgg.graph_config,
        jgg.morphed_task_graph,
        jgg.label_to_taskid,
        jgg.parameters,
        decision_task_id=decision_task_id,
    )


def get_decision_parameters(graph_config, options):
    """
    Load parameters from the command-line options for 'taskgraph decision'.
    This also applies per-project parameters, based on the given project.

    """
    parameters = {
        n: options[n]
        for n in [
            "base_repository",
            "head_repository",
            "head_rev",
            "head_ref",
            "head_tag",
            "project",
            "pushlog_id",
            "pushdate",
            "repository_type",
            "owner",
            "level",
            "target_tasks_method",
            "pipeline_source",
        ]
        if n in options
    }

    repo = get_repository(os.getcwd())
    commit_message = repo.get_commit_message()

    # Define default filter list, as most configurations shouldn't need
    # custom filters.
    parameters["filters"] = [
        "target_tasks_method",
    ]
    parameters["optimize_target_tasks"] = True
    parameters["existing_tasks"] = {}
    parameters["do_not_optimize"] = []

    # owner must be an email, but sometimes (e.g., for ffxbld) it is not, in which
    # case, fake it
    if "@" not in parameters["owner"]:
        parameters["owner"] += "@noreply.mozilla.org"

    # use the pushdate as build_date if given, else use current time
    parameters["build_date"] = parameters["pushdate"] or int(time.time())
    # moz_build_date is the build identifier based on build_date
    parameters["moz_build_date"] = time.strftime(
        "%Y%m%d%H%M%S", time.gmtime(parameters["build_date"])
    )

    project = parameters["project"]
    try:
        parameters.update(PER_PROJECT_PARAMETERS[project])
    except KeyError:
        logger.warning(
            "using default project parameters; add {} to "
            "PER_PROJECT_PARAMETERS in {} to customize behavior "
            "for this project".format(project, __file__)
        )
        parameters.update(PER_PROJECT_PARAMETERS["default"])

    # `target_tasks_method` has higher precedence than `project` parameters
    if options.get("target_tasks_method"):
        parameters["target_tasks_method"] = options["target_tasks_method"]

    # ..but can be overridden by the commit message: if it contains the special
    # string "DONTBUILD" and this is an on-push decision task, then use the
    # special 'nothing' target task method.
    if "DONTBUILD" in commit_message and options["pipeline_source"] == "push":
        parameters["target_tasks_method"] = "nothing"

    if options.get("optimize_target_tasks") is not None:
        parameters["optimize_target_tasks"] = options["optimize_target_tasks"]

    if "decision-parameters" in graph_config["taskgraph"]:
        find_object(graph_config["taskgraph"]["decision-parameters"])(
            graph_config, parameters
        )

    if options.get("try_task_config_file"):
        task_config_file = os.path.abspath(options.get("try_task_config_file"))
    else:
        # if try_task_config.json is present, load it
        task_config_file = os.path.join(os.getcwd(), "try_task_config.json")

    # load try settings
    if ("try" in project and options["pipeline_source"] == "push") or options[
        "pipeline_source"
    ] == "merge_request_event":
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