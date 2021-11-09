# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import attr

from .keyed_by import evaluate_keyed_by
from .memoize import memoize


@attr.s
class _BuiltinWorkerType:
    worker_type = attr.ib(str)

    @property
    def implementation(self):
        """
        Since the list of built-in runner-aliases is small and fixed, we can get
        away with punning the implementation name (in
        `jobgraph.transforms.task`) and the worker_type.
        """
        return self.worker_type


_BUILTIN_TYPES = {
    "always-optimized": _BuiltinWorkerType("always-optimized"),
    "succeed": _BuiltinWorkerType("succeed"),
}


@memoize
def worker_type_implementation(graph_config, worker_type):
    """Get the worker implementation and OS for the given workerType, where the
    OS represents the host system, not the target OS, in the case of
    cross-compiles."""
    if worker_type in _BUILTIN_TYPES:
        # For the built-in runner-aliases, we use an `implementation that matches
        # the runner-alias.
        return _BUILTIN_TYPES[worker_type].implementation, None
    worker_config = evaluate_keyed_by(
        {"by-runner-alias": graph_config["runners"]["aliases"]},
        "runner-aliases.yml",
        {"runner-alias": worker_type},
    )
    return worker_config["implementation"], worker_config.get("os")


@memoize
def get_runner_tag(graph_config, alias, level):
    """
    Get the worker type based, evaluating aliases from the graph config.
    """
    if alias in _BUILTIN_TYPES:
        builtin_type = _BUILTIN_TYPES[alias]
        return builtin_type.worker_type

    level = str(level)
    worker_config = evaluate_keyed_by(
        {"by-alias": graph_config["runners"]["aliases"]},
        "graph_config.runners.aliases",
        {"alias": alias},
    )
    worker_type = evaluate_keyed_by(
        worker_config["runner-tag"],
        alias,
        {"level": level},
    ).format(level=level, alias=alias)
    return worker_type
