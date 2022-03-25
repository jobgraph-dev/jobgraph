import json
import logging
import os
import time
from pathlib import Path

import yaml
from voluptuous import Optional

from jobgraph.util.python_path import find_object
from jobgraph.util.vcs import get_repository
from jobgraph.util.yaml import load_yaml

from .generator import JobGraphGenerator
from .jobgraph import JobGraph
from .parameters import Parameters
from .util.chunkify import chunkify
from .util.schema import Schema, validate_schema

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = "jobgraph-artifacts"

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

    _write_generated_gitlab_ci_yml(jgg)


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
            "pipeline_id",
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
        logger.info(f"using try jobs from {task_config_file}")
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
    logger.info(f"writing artifact file `{ARTIFACTS_DIR}/{filename}`")
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
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


# gitlab.com has a limit on the size of `.gitlab-ci.yml` (or any generated one)
# It's documented to be 1MB[1], but 350kb somehow triggered this error too.
# Thus, let's assume the threshold is much smaller.
#
# [1] https://docs.gitlab.com/ee/administration/instance_limits.html#maximum-size-and-depth-of-cicd-configuration-yaml-files    # noqa E501
GITLAB_CI_YML_THRESHOLD_SIZE_IN_BYTES = 250000


def _write_generated_gitlab_ci_yml(jobgraph_generator):
    generated_ci_jobs = jobgraph_generator.optimized_job_graph.to_gitlab_ci_jobs()
    generated_main_file_name = "generated-gitlab-ci.yml"
    output_path = Path(ARTIFACTS_DIR) / generated_main_file_name

    write_artifact(generated_main_file_name, generated_ci_jobs)

    number_of_files_to_generate = (
        output_path.stat().st_size // GITLAB_CI_YML_THRESHOLD_SIZE_IN_BYTES
    ) + 1

    if number_of_files_to_generate > 1:
        stages = generated_ci_jobs.pop("stages")
        includes = []

        all_jobs_names = tuple(sorted(generated_ci_jobs.keys()))

        for chunk in range(1, number_of_files_to_generate + 1):
            jobs_names_in_chunk = chunkify(
                all_jobs_names, chunk, number_of_files_to_generate
            )
            jobs_in_chunk = {
                job_name: job
                for job_name, job in generated_ci_jobs.items()
                if job_name in jobs_names_in_chunk
            }

            file_name = f"generated-include-{chunk}.yml"
            includes.append(
                {
                    "artifact": str(Path(ARTIFACTS_DIR) / file_name),
                    "job": "decision",
                }
            )
            write_artifact(file_name, jobs_in_chunk)

        write_artifact(
            generated_main_file_name, {"stages": stages, "include": includes}
        )


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
