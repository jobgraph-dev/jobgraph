import argparse
import atexit
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from collections import namedtuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import appdirs
import yaml

from jobgraph.util.gitlab import GITLAB_DEFAULT_ROOT_URL
from jobgraph.util.strtobool import strtobool

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


def get_filtered_jobgraph(jobgraph, jobsregex):
    """
    Filter all the jobs on basis of a regular expression
    and returns a new JobGraph object
    """
    from jobgraph.graph import Graph
    from jobgraph.jobgraph import JobGraph

    # return original jobgraph if no regular expression is passed
    if not jobsregex:
        return jobgraph
    named_links_dict = jobgraph.graph.named_links_dict()
    filteredjobs = {}
    filterededges = set()
    regexprogram = re.compile(jobsregex)

    for key in jobgraph.graph.visit_postorder():
        task = jobgraph.jobs[key]
        if regexprogram.match(task.label):
            filteredjobs[key] = task
            for depname, dep in named_links_dict[key].items():
                if regexprogram.match(dep):
                    filterededges.add((key, dep, depname))
    filtered_jobgraph = JobGraph(filteredjobs, Graph(set(filteredjobs), filterededges))
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
            overrides={"target-stage": options.get("target_stage")},
            strict=False,
        )

    tgg = get_jobgraph_generator(options.get("root"), parameters)

    tg = getattr(tgg, options["graph_attr"])
    tg = get_filtered_jobgraph(tg, options["jobs_regex"])
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
            f"Dumping result with parameters from {params_name}:",
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
            f"{options['graph_attr']}_{Parameters.format_spec(spec)}.log",
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
    "jobs",
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
    defaults={"graph_attr": "target_job_graph"},
)
@command(
    "optimized",
    help="Show the optimized graph.",
    defaults={"graph_attr": "optimized_job_graph"},
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
    ".json), a directory (containing "
    "parameters files). Can be specified multiple times, in which case multiple "
    "generations will happen from the same invocation (one per parameters "
    "specified).",
)
@argument(
    "--no-optimize",
    dest="optimize",
    action="store_false",
    default="true",
    help="do not remove jobs from the graph that are found in the "
    "index (a.k.a. optimize the graph)",
)
@argument(
    "-o",
    "--output-file",
    default=None,
    help="file path to store generated output.",
)
@argument(
    "--jobs-regex",
    "--jobs",
    default=None,
    help="only return jobs with labels matching this regular " "expression.",
)
@argument(
    "--target-stage",
    default=None,
    help="only return jobs that are of the given stage, or their dependencies.",
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

    parameters: list[Any[str, Parameters]] = options.pop("parameters")
    if not parameters:
        kwargs = {
            "target-stage": options.get("target_stage"),
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
                    capture_output=True,
                    text=True,
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
        print(f"See '{logdir}' for logs", file=sys.stderr)


@command(
    "image-context-hash",
    help="Print the context hash of a docker image. This hash used as the tag.",
)
@argument(
    "image_name",
    help="Print the context hash of the image of this name based on the current "
    "contents of the tree.",
)
def image_digest(args):
    from jobgraph.docker import get_image_context_hash

    try:
        digest = get_image_context_hash(args["image_name"])
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
@argument("--owner", required=True, help="email address of who owns this graph")
@argument(
    "--is-head-ref-protected",
    # This argument is written in an usual way for 2 reasons:
    #   1. It's not a flag (as in we define it with `store_true`) because it's
    #      just easier to keep this argument around no matter the value of
    #      $CI_COMMIT_REF_PROTECTED.
    #   2. It doesn't store a boolean (which was originally the case) because
    #      functions like resolve_keyed_by() only work with strings.
    #
    # This is why we convert a string which conveys boolean information into
    # another string that stores 2 states.
    type=lambda x: "protected" if strtobool(x) else "unprotected",
    dest="head_ref_protection",
    required=True,
    help="boolean that expresses whether the current git ref is protected on Gitlab. "
    "You usually want to pass $CI_COMMIT_REF_PROTECTED to this argument",
)
@argument(
    "--target-jobs-method",
    default="default",
    help="method for selecting the target jobs to generate",
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
    "--pipeline-id",
    help="The pipeline ID the decision job runs in",
    default="",
)
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


@command(
    "update-dependencies",
    help="Update all dependencies defined in jobgraph (Docker base images, "
    "python packages, etc.)",
)
@argument(
    "--new-merge-request",
    action="store_true",
    dest="create_new_merge_request",
    help="Create a new merge request if any changes can be committed",
)
@argument(
    "--git-committer-name",
    help="Name to use in the git commit",
    default="jobgraph-bot",
)
@argument(
    "--git-committer-email",
    help="Email address to use in the git commit",
    required="--new-merge-request" in sys.argv,
)
@argument(
    "--git-remote-name",
    help="Name of the remote repository",
    default="origin",
)
@argument(
    "--git-branch",
    help="Git branch to create the merge request from",
    default="update-jobgraph-dependencies",
)
def update_depdencies(options):
    from jobgraph.update_dependencies import update_dependencies

    options.pop("command")
    update_dependencies(**options)


@command(
    "bootstrap",
    help="Create files to get started with jobgraph",
)
@argument(
    "--gitlab-project-id",
    required=True,
    type=int,
    help="Project ID of the current Gitlab repository",
)
@argument(
    "--gitlab-root-url",
    default=GITLAB_DEFAULT_ROOT_URL,
    help=f"Root URL of the Gitlab instance (default: {GITLAB_DEFAULT_ROOT_URL})",
)
@argument(
    "--jobgraph-bot-username",
    required=True,
    help="Account that will regularly update jobgraph.",
)
@argument(
    "--jobgraph-bot-gitlab-token",
    required=True,
    help="Gitlab token that let jobgraph update Gitlab CI schedules based on a file "
    "stored on the repo an monitored by jobgraph. Token must have the `api` scope",
)
@argument(
    "--maintainer-username",
    required=True,
    help="Gitlab username that will setup repository secrets to let jobgraph update "
    "Gitlab CI schedules. Username must be the owner of the supplied token. Gitlab "
    "user must have at least the `maintainer` role.",
)
@argument(
    "--maintainer-gitlab-token",
    required=True,
    help="Gitlab token owned by the maintainer",
)
def bootstrap(options):
    from jobgraph.bootstrap import bootstrap

    options.pop("command")
    bootstrap(**options)


def create_parser():
    parser = argparse.ArgumentParser(description="Interact with jobgraph")
    subparsers = parser.add_subparsers()
    for _, (func, args, kwargs, defaults) in commands.items():
        subparser = subparsers.add_parser(*args, **kwargs)
        func_args = getattr(func, "args", [])
        for arg in func_args:
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
