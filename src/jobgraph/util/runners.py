import attr

from .keyed_by import evaluate_keyed_by
from .memoize import memoize


@attr.s
class _BuiltinRunnerAlias:
    runner_tag = attr.ib(str)

    @property
    def implementation(self):
        """
        Since the list of built-in runner_aliases is small and fixed, we can get
        away with punning the implementation name (in
        `jobgraph.transforms.task`) and the runner_tag.
        """
        return self.runner_tag


_BUILTIN_TYPES = {
    "always-optimized": _BuiltinRunnerAlias("always-optimized"),
    "succeed": _BuiltinRunnerAlias("succeed"),
}


@memoize
def get_runner_alias_implementation(graph_config, runner_alias):
    """Get the runner implementation and OS for the given runner_alias, where the
    OS represents the host system, not the target OS, in the case of
    cross-compiles."""
    if runner_alias in _BUILTIN_TYPES:
        # For the built-in runner_aliases, we use an `implementation that matches
        # the runner_alias.
        return _BUILTIN_TYPES[runner_alias].implementation, None
    runner_config = evaluate_keyed_by(
        {"by_runner_alias": graph_config["runners"]["aliases"]},
        "runner_aliases.yml",
        {"runner_alias": runner_alias},
    )
    return runner_config["implementation"], runner_config.get("os")


@memoize
def get_runner_tag(graph_config, alias, head_ref_protection):
    """
    Get the runner type based, evaluating aliases from the graph config.
    """
    if alias in _BUILTIN_TYPES:
        builtin_type = _BUILTIN_TYPES[alias]
        return builtin_type.runner_tag

    head_ref_protection = str(head_ref_protection)
    runner_config = evaluate_keyed_by(
        {"by_alias": graph_config["runners"]["aliases"]},
        "graph_config.runners.aliases",
        {"alias": alias},
    )
    runner_tag = evaluate_keyed_by(
        runner_config["runner_tag"],
        alias,
        {"head_ref_protection": head_ref_protection},
    ).format(alias=alias)
    return runner_tag
