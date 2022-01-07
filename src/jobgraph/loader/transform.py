import logging

from ..util.templates import merge
from ..util.yaml import load_yaml

logger = logging.getLogger(__name__)


def loader(stage, path, config, params, loaded_jobs):
    """
    Get the input elements that will be transformed into jobs in a generic
    way.  The elements themselves are free-form, and become the input to the
    first transform.

    By default, this reads jobs from the `jobs` key, or from yaml files
    named by `jobs_from`.  The entities are read from mappings, and the
    keys to those mappings are added in the `name` key of each entity.

    If there is a `job_defaults` config, then every job is merged with it.
    This provides a simple way to set default values for all jobs of a stage.
    The `job_defaults` key can also be specified in a yaml file pointed to by
    `jobs_from`. In this case it will only apply to jobs defined in the same
    file.

    Other stage implementations can use a different loader function to
    produce inputs and hand them to `transform_inputs`.
    """

    def jobs():
        defaults = config.get("job_defaults")
        for name, job in config.get("jobs", {}).items():
            if defaults:
                job = merge(defaults, job)
            job["job_from"] = "stage.yml"
            yield name, job

        for filename in config.get("jobs_from", []):
            jobs = load_yaml(path, filename)

            file_defaults = jobs.pop("job_defaults", None)
            if defaults:
                file_defaults = merge(defaults, file_defaults or {})

            for name, job in jobs.items():
                if file_defaults:
                    job = merge(file_defaults, job)
                job["job_from"] = filename
                yield name, job

    for name, job in jobs():
        job["name"] = name
        set_cache_upstream_jobs(job, loaded_jobs)
        logger.debug(f"Generating jobs for {stage} {name}")
        yield job


def set_cache_upstream_jobs(job, loaded_jobs):
    job_names_to_pull_cache_from = job.pop("pull_caches_from_jobs", None)

    if job_names_to_pull_cache_from:
        if type(job_names_to_pull_cache_from) != list:
            raise ValueError(f"Job {job['name']} must provide a list of job names")

        cache_dependencies = []

        for job_name in job_names_to_pull_cache_from:
            for loaded_job in loaded_jobs:
                if job_name == loaded_job.label:
                    cache_dependencies.append(loaded_job)
                    break
            else:
                raise ValueError(f"Couldn't find job {job_name} in loaded jobs")

        job["upstream_cache_jobs"] = cache_dependencies
