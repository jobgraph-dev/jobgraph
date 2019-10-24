# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

import os
import re
import sys
import traceback
import argparse
import logging
import json
import yaml

_commands = []


def command(*args, **kwargs):
    defaults = kwargs.pop("defaults", {})

    def decorator(func):
        _commands.append((func, args, kwargs, defaults))
        return func

    return decorator


def argument(*args, **kwargs):
    def decorator(func):
        if not hasattr(func, "args"):
            func.args = []
        func.args.append((args, kwargs))
        return func

    return decorator


def show_taskgraph_labels(taskgraph):
    for index in taskgraph.graph.visit_postorder():
        print(taskgraph.tasks[index].label)


def show_taskgraph_json(taskgraph):
    print(
        json.dumps(
            taskgraph.to_json(), sort_keys=True, indent=2, separators=(",", ": ")
        )
    )


def show_taskgraph_yaml(taskgraph):
    print(yaml.safe_dump(taskgraph.to_json(), default_flow_style=False))


def get_filtered_taskgraph(taskgraph, tasksregex):
    """
    Filter all the tasks on basis of a regular expression
    and returns a new TaskGraph object
    """
    from taskgraph.graph import Graph
    from taskgraph.taskgraph import TaskGraph

    # return original taskgraph if no regular expression is passed
    if not tasksregex:
        return taskgraph
    named_links_dict = taskgraph.graph.named_links_dict()
    filteredtasks = {}
    filterededges = set()
    regexprogram = re.compile(tasksregex)

    for key in taskgraph.graph.visit_postorder():
        task = taskgraph.tasks[key]
        if regexprogram.match(task.label):
            filteredtasks[key] = task
            for depname, dep in named_links_dict[key].iteritems():
                if regexprogram.match(dep):
                    filterededges.add((key, dep, depname))
    filtered_taskgraph = TaskGraph(
        filteredtasks, Graph(set(filteredtasks), filterededges)
    )
    return filtered_taskgraph


SHOW_METHODS = {
    "labels": show_taskgraph_labels,
    "json": show_taskgraph_json,
    "yaml": show_taskgraph_yaml,
}


@command(
    "full", help="Show the full taskgraph.", defaults={"graph_attr": "full_task_graph"}
)
@command(
    "target",
    help="Show the set of target tasks.",
    defaults={"graph_attr": "target_task_set"},
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
    defaults={"graph_attr": "morphed_task_graph"},
)
@argument("--root", "-r", help="root of the taskgraph definition relative to topsrcdir")
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
    default="",
    help="parameters file (.yml or .json; see " "`taskcluster/docs/parameters.rst`)`",
)
@argument(
    "--no-optimize",
    dest="optimize",
    action="store_false",
    default="true",
    help="do not remove tasks from the graph that are found in the "
    "index (a.k.a. ptimize the graph)",
)
@argument(
    "--tasks-regex",
    "--tasks",
    default=None,
    help="only return tasks with labels matching this regular " "expression.",
)
@argument(
    "-F",
    "--fast",
    dest="fast",
    default=False,
    action="store_true",
    help="enable fast task generation for local debugging.",
)
def show_taskgraph(options):
    import taskgraph.parameters
    import taskgraph.target_tasks
    import taskgraph.generator
    import taskgraph

    if options["fast"]:
        taskgraph.fast = True

    try:
        parameters = taskgraph.parameters.parameters_loader(
            options["parameters"], strict=False
        )

        tgg = taskgraph.generator.TaskGraphGenerator(
            root_dir=options.get("root"), parameters=parameters
        )

        tg = getattr(tgg, options["graph_attr"])

        show_method = SHOW_METHODS.get(options["format"] or "labels")
        tg = get_filtered_taskgraph(tg, options["tasks_regex"])
        show_method(tg)
    except Exception:
        traceback.print_exc()
        sys.exit(1)


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
    from taskgraph.docker import build_image, build_context

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
    from taskgraph.docker import load_image_by_name, load_image_by_task_id

    if not args.get("image_name") and not args.get("task_id"):
        print("Specify either IMAGE-NAME or TASK-ID")
        sys.exit(1)
    try:
        if args["task_id"]:
            ok = load_image_by_task_id(args["task_id"], args.get("tag"))
        else:
            ok = load_image_by_name(args["image_name"], args.get("tag"))
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
    from taskgraph.docker import get_image_digest

    try:
        digest = get_image_digest(args["image_name"])
        print(digest)
    except Exception:
        traceback.print_exc()
        sys.exit(1)


@command("decision", help="Run the decision task")
@argument("--root", "-r", help="root of the taskgraph definition relative to topsrcdir")
@argument(
    "--message",
    required=True,
    help='Commit message to be parsed. Example: "try: -b do -p all -u all"',
)
@argument(
    "--project",
    required=True,
    help="Project to use for creating task graph. Example: --project=try",
)
@argument("--pushlog-id", dest="pushlog_id", required=True, default=0)
@argument("--pushdate", dest="pushdate", required=True, type=int, default=0)
@argument("--owner", required=True, help="email address of who owns this graph")
@argument("--level", required=True, help="SCM level of this repository")
@argument(
    "--target-tasks-method", help="method for selecting the target tasks to generate"
)
@argument(
    "--repository-type", required=True, help='Type of repository, either "hg" or "git"'
)
@argument("--base-repository", required=True, help='URL for "base" repository to clone')
@argument(
    "--head-repository",
    required=True,
    help='URL for "head" repository to fetch revision from',
)
@argument(
    "--head-ref", required=True, help="Reference (this is same as rev usually for hg)"
)
@argument(
    "--head-rev", required=True, help="Commit revision to use from head repository"
)
@argument(
    "--tasks-for", required=True, help="the tasks_for value used to generate this task"
)
def decision(options):
    from taskgraph.decision import taskgraph_decision

    taskgraph_decision(options)


@command("cron", help="Run the cron task")
@argument("--head-repository", required=True, help='URL for "head" repository to fetch')
@argument("--head-ref", required=False, help="Reference, this is required for git")
@argument(
    "--repository-type", required=True, help='Type of repository, either "hg" or "git"'
)
@argument(
    "--project",
    required=True,
    help="Project to use for creating tasks. Example: --project=mozilla-central",
)
@argument("--level", required=True, help="SCM level of this repository")
@argument(
    "--force-run",
    required=False,
    help="If given, force this cronjob to run regardless of time, " "and run no others",
)
@argument(
    "--no-create",
    required=False,
    action="store_true",
    help="Do not actually create tasks",
)
@argument(
    "--root",
    "-r",
    required=False,
    help="root of the repository to get cron task definitions from",
)
def taskgraph_cron(options):
    """Run the cron task; this task creates zero or more decision tasks.  It is run
    from the hooks service on a regular basis."""
    import taskgraph.cron

    return taskgraph.cron.taskgraph_cron(options)


def create_parser():
    parser = argparse.ArgumentParser(description="Interact with taskgraph")
    subparsers = parser.add_subparsers()
    for (func, args, kwargs, defaults) in _commands:
        subparser = subparsers.add_parser(*args, **kwargs)
        for arg in func.args:
            subparser.add_argument(*arg[0], **arg[1])
        subparser.set_defaults(command=func, **defaults)
    return parser


def main():
    logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
    parser = create_parser()
    args = parser.parse_args()
    try:
        args.command(vars(args))
    except Exception:
        traceback.print_exc()
        sys.exit(1)
