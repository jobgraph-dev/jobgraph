import copy

from voluptuous import Required

from jobgraph.job import Job
from jobgraph.util.schema import Schema

from . import group_jobs

schema = Schema(
    {
        Required("primary_dependency", "primary dependency job"): Job,
        Required(
            "dependent_jobs",
            "dictionary of dependent jobs, keyed by kind",
        ): {str: Job},
    }
)


def loader(kind, path, config, params, loaded_jobs):
    """
    Load jobs based on the jobs dependant kinds, designed for use as
    multiple-dependent needs.
    Required ``group-by-fn`` is used to define how we coalesce the
    multiple deps together to pass to transforms, e.g. all kinds specified get
    collapsed by platform with `platform`
    Optional ``primary_dependency`` (ordered list or string) is used to determine
    which upstream kind to inherit attrs from. See ``get_primary_dep``.
    The `only-for-build-type` kind configuration, if specified, will limit
    the build types for which a job will be created.
    Optional ``job-template`` kind configuration value, if specified, will be used to
    pass configuration down to the specified transforms used.
    """
    job_defaults = config.get("job_defaults")

    for dep_jobs in group_jobs(config, loaded_jobs):
        kinds = [dep.stage for dep in dep_jobs]
        assert_unique_members(
            kinds,
            error_msg="multi_dep.py should have filtered down to one job per kind",
        )

        dep_jobs_per_kind = {dep.stage: dep for dep in dep_jobs}

        job = {"dependent_jobs": dep_jobs_per_kind}
        job["primary_dependency"] = get_primary_dep(config, dep_jobs_per_kind)
        if job_defaults:
            job.update(copy.deepcopy(job_defaults))

        yield job


def assert_unique_members(kinds, error_msg=None):
    if len(kinds) != len(set(kinds)):
        raise Exception(error_msg)


def get_primary_dep(config, dep_jobs):
    """Find the dependent job to inherit attributes from.
    If ``primary_dependency`` is defined in ``kind.yml`` and is a string,
    then find the first dep with that job kind and return it. If it is
    defined and is a list, the first kind in that list with a matching dep
    is the primary dependency. If it's undefined, return the first dep.
    """
    primary_dependencies = config.get("primary_dependency")
    if isinstance(primary_dependencies, str):
        primary_dependencies = [primary_dependencies]
    if not primary_dependencies:
        assert len(dep_jobs) == 1, "Must define a primary_dependency!"
        return list(dep_jobs.values())[0]
    primary_dep = None
    for primary_kind in primary_dependencies:
        for dep_kind in dep_jobs:
            if dep_kind == primary_kind:
                assert (
                    primary_dep is None
                ), "Too many primary dependent jobs in dep_jobs: {}!".format(
                    [t.label for t in dep_jobs]
                )
                primary_dep = dep_jobs[dep_kind]
    if primary_dep is None:
        raise Exception(
            f"Can't find dependency of {config['primary_dependency']}: {config}"
        )
    return primary_dep
