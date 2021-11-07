# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import atexit
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import argparse
import logging
import json
from collections import namedtuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, List

import appdirs
import yaml

Command = namedtuple("Command", ["func", "args", "kwargs", "defaults"])
commands = {}


def command(*args, **kwargs):
    defaults = kwargs.pop("defaults", {})

    def decorator(func):
        commands[args[0]] = Command(func, args, kwargs, defaults)
        return func

    return decorator


def argument(*args, **kwargs):
    def decorator(func):
        if not hasattr(func, "args"):
            func.args = []
        func.args.append((args, kwargs))
        return func

    return decorator


def format_jobgraph_labels(jobgraph):
    return "\n".join(
        jobgraph.jobs[index].label for index in jobgraph.graph.visit_postorder()
    )


def format_jobgraph_json(jobgraph):
    return json.dumps(
        jobgraph.to_json(), sort_keys=True, indent=2, separators=(",", ": ")
    )


def format_jobgraph_yaml(jobgraph):
    return yaml.safe_dump(jobgraph.to_json(), default_flow_style=False)


def get_filtered_jobgraph(jobgraph, tasksregex):
    """
    Filter all the tasks on basis of a regular expression
    and returns a new JobGraph object
    """
    from jobgraph.graph import Graph
    from jobgraph.jobgraph import JobGraph

    # return original jobgraph if no regular expression is passed
    if not tasksregex:
        return jobgraph
    named_links_dict = jobgraph.graph.named_links_dict()
    filteredtasks = {}
    filterededges = set()
    regexprogram = re.compile(tasksregex)

    for key in jobgraph.graph.visit_postorder():
        task = jobgraph.jobs[key]
        if regexprogram.match(task.label):
            filteredtasks[key] = task
            for depname, dep in named_links_dict[key].items():
                if regexprogram.match(dep):
                    filterededges.add((key, dep, depname))
    filtered_jobgraph = JobGraph(
        filteredtasks, Graph(set(filteredtasks), filterededges)
    )
    return filtered_jobgraph


FORMAT_METHODS = {
    "labels": format_jobgraph_labels,
    "json": format_jobgraph_json,
    "txt": format_jobgraph_labels,
    "yaml": format_jobgraph_yaml,
    "yml": format_jobgraph_yaml,
}


def get_jobgraph_generator(root, parameters):
    """Helper function to make testing a little easier."""
    from jobgraph.generator import JobGraphGenerator

    return JobGraphGenerator(root_dir=root, parameters=parameters)


def format_jobgraph(options, parameters, logfile=None):
    import jobgraph
    from jobgraph.parameters import parameters_loader

    if logfile:
        oldhandler = logging.root.handlers[-1]
        logging.root.removeHandler(oldhandler)

        handler = logging.FileHandler(logfile, mode="w")
        handler.setFormatter(oldhandler.formatter)
        logging.root.addHandler(handler)

    if options["fast"]:
        jobgraph.fast = True

    if isinstance(parameters, str):
        parameters = parameters_loader(
            parameters,
            overrides={"target-kind": options.get("target_kind")},
            strict=False,
        )

    tgg = get_jobgraph_generator(options.get("root"), parameters)

    tg = getattr(tgg, options["graph_attr"])
    tg = get_filtered_jobgraph(tg, options["tasks_regex"])
    format_method = FORMAT_METHODS[options["format"] or "labels"]
    return format_method(tg)


def dump_output(out, path=None, params_spec=None):
    from jobgraph.parameters import Parameters

    params_name = Parameters.format_spec(params_spec)
    fh = None
    if path:
        # Substitute params name into file path if necessary
        if params_spec and "{params}" not in path:
            name, ext = os.path.splitext(path)
            name += "_{params}"
            path = name + ext

        path = path.format(params=params_name)
        fh = open(path, "w")
    else:
        print(
            "Dumping result with parameters from {}:".format(params_name),
            file=sys.stderr,
        )
    print(out + "\n", file=fh)


def generate_jobgraph(options, parameters, logdir):
    from jobgraph.parameters import Parameters

    def logfile(spec):
        """Determine logfile given a parameters specification."""
        if logdir is None:
            return None
        return os.path.join(
            logdir,
            "{}_{}.log".format(options["graph_attr"], Parameters.format_spec(spec)),
        )

    # Don't bother using futures if there's only one parameter. This can make
    # tracebacks a little more readable and avoids additional process overhead.
    if len(parameters) == 1:
        spec = parameters[0]
        out = format_jobgraph(options, spec, logfile(spec))
        dump_output(out, options["output_file"])
        return

    futures = {}
    with ProcessPoolExecutor() as executor:
        for spec in parameters:
            f = executor.submit(format_jobgraph, options, spec, logfile(spec))
            futures[f] = spec

    for future in as_completed(futures):
        output_file = options["output_file"]
        spec = futures[future]
        e = future.exception()
        if e:
            out = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            if options["diff"]:
                # Dump to console so we don't accidentally diff the tracebacks.
                output_file = None
        else:
            out = future.result()

        dump_output(
            out,
            path=output_file,
            params_spec=spec if len(parameters) > 1 else None,
        )


@command(
    "tasks",
    help="Show all jobs in the jobgraph.",
    defaults={"graph_attr": "full_job_set"},
)
@command(
    "full", help="Show the full jobgraph.", defaults={"graph_attr": "full_job_graph"}
)
@command(
    "target",
    help="Show the set of target jobs.",
    defaults={"graph_attr": "target_job_set"},
)
@command(
    "target-graph",
    help="Show the target graph.",
    defaults={"graph_attr": "target_task_graph"},
)
@command(
    "optimized",
    help="Show the optimized graph.",
    defaults={"graph_attr": "optimized_task_graph"},
)
@command(
    "morphed",
    help="Show the morphed graph.",
    defaults={"graph_attr": "morphed_job_graph"},
)
@argument("--root", "-r", help="root of the jobgraph definition relative to topsrcdir")
@argument("--quiet", "-q", action="store_true", help="suppress all logging output")
@argument(
    "--verbose", "-v", action="store_true", help="include debug-level logging output"
)
@argument(
    "--json",
    "-J",
    action="store_const",
    dest="format",
    const="json",
    help="Output task graph as a JSON object",
)
@argument(
    "--yaml",
    "-Y",
    action="store_const",
    dest="format",
    const="yaml",
    help="Output task graph as a YAML object",
)
@argument(
    "--labels",
    "-L",
    action="store_const",
    dest="format",
    const="labels",
    help="Output the label for each task in the task graph (default)",
)
@argument(
    "--parameters",
    "-p",
    default=None,
    action="append",
    help="Parameters to use for the generation. Can be a path to file (.yml or "
    ".json; see `taskcluster/docs/parameters.rst`), a directory (containing "
    "parameters files), a url, of the form `project=mozilla-central` to download "
    "latest parameters file for the specified project from CI, or of the form "
    "`task-id=<decision task id>` to download parameters from the specified "
    "decision task. Can be specified multiple times, in which case multiple "
    "generations will happen from the same invocation (one per parameters "
    "specified).",
)
@argument(
    "--no-optimize",
    dest="optimize",
    action="store_false",
    default="true",
    help="do not remove tasks from the graph that are found in the "
    "index (a.k.a. optimize the graph)",
)
@argument(
    "-o",
    "--output-file",
    default=None,
    help="file path to store generated output.",
)
@argument(
    "--tasks-regex",
    "--tasks",
    default=None,
    help="only return tasks with labels matching this regular " "expression.",
)
@argument(
    "--target-kind",
    default=None,
    help="only return tasks that are of the given kind, or their dependencies.",
)
@argument(
    "-F",
    "--fast",
    default=False,
    action="store_true",
    help="enable fast task generation for local debugging.",
)
@argument(
    "--diff",
    const="default",
    nargs="?",
    default=None,
    help="Generate and diff the current jobgraph against another revision. "
    "Without args the base revision will be used. A revision specifier such as "
    "the hash or `HEAD~1` can be used as well.",
)
def show_jobgraph(options):
    from jobgraph.parameters import Parameters
    from jobgraph.util.vcs import get_repository

    if options.pop("verbose", False):
        logging.root.setLevel(logging.DEBUG)

    repo = None
    cur_ref = None
    diffdir = None
    output_file = options["output_file"]

    if output_file and not options.get("format"):
        options["format"] = Path(output_file).suffix[1:]

    if options["diff"]:
        repo = get_repository(os.getcwd())

        if not repo.working_directory_clean():
            print(
                "abort: can't diff jobgraph with dirty working directory",
                file=sys.stderr,
            )
            return 1

        # We want to return the working directory to the current state
        # as best we can after we're done. In all known cases, using
        # branch or bookmark (which are both available on the VCS object)
        # as `branch` is preferable to a specific revision.
        cur_ref = repo.branch or repo.head_ref[:12]

        diffdir = tempfile.mkdtemp()
        atexit.register(
            shutil.rmtree, diffdir
        )  # make sure the directory gets cleaned up
        options["output_file"] = os.path.join(
            diffdir, f"{options['graph_attr']}_{cur_ref}"
        )
        print(f"Generating {options['graph_attr']} @ {cur_ref}", file=sys.stderr)

    parameters: List[Any[str, Parameters]] = options.pop("parameters")
    if not parameters:
        kwargs = {
            "target-kind": options.get("target_kind"),
        }
        parameters = [Parameters(strict=False, **kwargs)]  # will use default values

    for param in parameters[:]:
        if isinstance(param, str) and os.path.isdir(param):
            parameters.remove(param)
            parameters.extend(
                [
                    p.as_posix()
                    for p in Path(param).iterdir()
                    if p.suffix in (".yml", ".json")
                ]
            )

    logdir = None
    if len(parameters) > 1:
        # Log to separate files for each process instead of stderr to
        # avoid interleaving.
        basename = os.path.basename(os.getcwd())
        logdir = os.path.join(appdirs.user_log_dir("jobgraph"), basename)
        if not os.path.isdir(logdir):
            os.makedirs(logdir)
    else:
        # Only setup logging if we have a single parameter spec. Otherwise
        # logging will go to files. This is also used as a hook for Gecko
        # to setup its `mach` based logging.
        setup_logging()

    generate_jobgraph(options, parameters, logdir)

    if options["diff"]:
        assert diffdir is not None
        assert repo is not None

        # Some transforms use global state for checks, so will fail
        # when running jobgraph a second time in the same session.
        # Reload all jobgraph modules to avoid this.
        for mod in sys.modules.copy():
            if mod != __name__ and mod.startswith("jobgraph"):
                del sys.modules[mod]

        if options["diff"] == "default":
            base_ref = repo.base_ref
        else:
            base_ref = options["diff"]

        try:
            repo.update(base_ref)
            base_ref = repo.head_ref[:12]
            options["output_file"] = os.path.join(
                diffdir, f"{options['graph_attr']}_{base_ref}"
            )
            print(f"Generating {options['graph_attr']} @ {base_ref}", file=sys.stderr)
            generate_jobgraph(options, parameters, logdir)
        finally:
            repo.update(cur_ref)

        # Generate diff(s)
        diffcmd = [
            "diff",
            "-U20",
            "--report-identical-files",
            f"--label={options['graph_attr']}@{base_ref}",
            f"--label={options['graph_attr']}@{cur_ref}",
        ]

        for spec in parameters:
            base_path = os.path.join(diffdir, f"{options['graph_attr']}_{base_ref}")
            cur_path = os.path.join(diffdir, f"{options['graph_attr']}_{cur_ref}")

            params_name = None
            if len(parameters) > 1:
                params_name = Parameters.format_spec(spec)
                base_path += f"_{params_name}"
                cur_path += f"_{params_name}"

            try:
                proc = subprocess.run(
                    diffcmd + [base_path, cur_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    check=True,
                )
                diff_output = proc.stdout
                returncode = 0
            except subprocess.CalledProcessError as e:
                # returncode 1 simply means diffs were found
                if e.returncode != 1:
                    print(e.stderr, file=sys.stderr)
                    raise
                diff_output = e.output
                returncode = e.returncode

            dump_output(
                diff_output,
                # Don't bother saving file if no diffs were found. Log to
                # console in this case instead.
                path=None if returncode == 0 else output_file,
                params_spec=spec if len(parameters) > 1 else None,
            )

        if options["format"] != "json":
            print(
                "If you were expecting differences in task bodies "
                'you should pass "-J"\n',
                file=sys.stderr,
            )

    if len(parameters) > 1:
        print("See '{}' for logs".format(logdir), file=sys.stderr)


@command("build-image", help="Build a Docker image")
@argument("image_name", help="Name of the image to build")
@argument(
    "-t", "--tag", help="tag that the image should be built as.", metavar="name:tag"
)
@argument(
    "--context-only",
    help="File name the context tarball should be written to."
    "with this option it will only build the context.tar.",
    metavar="context.tar",
)
def build_image(args):
    from jobgraph.docker import build_image, build_context

    if args["context_only"] is None:
        build_image(args["image_name"], args["tag"], os.environ)
    else:
        build_context(args["image_name"], args["context_only"], os.environ)


@command(
    "load-image",
    help="Load a pre-built Docker image. Note that you need to "
    "have docker installed and running for this to work.",
)
@argument(
    "--task-id",
    help="Load the image at public/image.tar.zst in this task, "
    "rather than searching the index",
)
@argument(
    "-t",
    "--tag",
    help="tag that the image should be loaded as. If not "
    "image will be loaded with tag from the tarball",
    metavar="name:tag",
)
@argument(
    "image_name",
    nargs="?",
    help="Load the image of this name based on the current "
    "contents of the tree (as built for mozilla-central "
    "or mozilla-inbound)",
)
def load_image(args):
    from jobgraph.docker import load_image_by_task_id

    if not args.get("image_name") and not args.get("task_id"):
        print("Specify either IMAGE-NAME or TASK-ID")
        sys.exit(1)
    try:
        if args["task_id"]:
            ok = load_image_by_task_id(args["task_id"], args.get("tag"))
        if not ok:
            sys.exit(1)
    except Exception:
        traceback.print_exc()
        sys.exit(1)


@command("image-digest", help="Print the digest of a docker image.")
@argument(
    "image_name",
    help="Print the digest of the image of this name based on the current "
    "contents of the tree.",
)
def image_digest(args):
    from jobgraph.docker import get_image_digest

    try:
        digest = get_image_digest(args["image_name"])
        print(digest)
    except Exception:
        traceback.print_exc()
        sys.exit(1)


@command("decision", help="Run the decision task")
@argument("--root", "-r", help="root of the jobgraph definition relative to topsrcdir")
@argument(
    "--message",
    required=False,
    help=argparse.SUPPRESS,
)
@argument(
    "--project",
    required=True,
    help="Project to use for creating task graph. Example: --project=try",
)
@argument("--pushdate", dest="pushdate", required=True, type=int, default=0)
@argument("--owner", required=True, help="email address of who owns this graph")
@argument("--level", required=True, help="SCM level of this repository")
@argument(
    "--target-tasks-method", help="method for selecting the target tasks to generate"
)
@argument("--base-repository", required=True, help='URL for "base" repository to clone')
@argument(
    "--base-rev",
    required=True,
    help="The previous latest commit present on a branch. If set to "
    '"0000000000000000000000000000000000000000", then jobgraph will '
    "determine the most recent ancestor between the current revision "
    "and the main branch",
)
@argument(
    "--head-repository",
    required=True,
    help='URL for "head" repository to fetch revision from',
)
@argument(
    "--head-ref",
    required=True,
    help="Commit reference (branch name or tag, for instance)",
)
@argument(
    "--head-rev", required=True, help="Commit revision to use from head repository"
)
@argument("--head-tag", help="Tag attached to the revision", default="")
@argument(
    "--pipeline-source",
    required=True,
    help="the pipeline_source value used to generate this task",
    # List defined in CI_PIPELINE_SOURCE at
    # https://docs.gitlab.com/ee/ci/variables/predefined_variables.html
    choices=(
        "api",
        "chat",
        "external_pull_request_event",
        "external",
        "merge_request_event",
        "parent_pipeline",
        "pipeline",
        "push",
        "schedule",
        "trigger",
        "web",
        "webide",
    ),
)
@argument("--try-task-config-file", help="path to try task configuration file")
def decision(options):
    from jobgraph.decision import jobgraph_decision

    jobgraph_decision(options)


def create_parser():
    parser = argparse.ArgumentParser(description="Interact with jobgraph")
    subparsers = parser.add_subparsers()
    for _, (func, args, kwargs, defaults) in commands.items():
        subparser = subparsers.add_parser(*args, **kwargs)
        for arg in func.args:
            subparser.add_argument(*arg[0], **arg[1])
        subparser.set_defaults(command=func, **defaults)
    return parser


def setup_logging():
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
    )


def main(args=sys.argv[1:]):
    setup_logging()
    parser = create_parser()
    args = parser.parse_args(args)
    try:
        args.command(vars(args))
    except Exception:
        traceback.print_exc()
        sys.exit(1)
