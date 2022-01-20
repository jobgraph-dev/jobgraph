import logging

from ..util.chunkify import chunkify
from ..util.templates import merge
from ..util.yaml import load_yaml

logger = logging.getLogger(__name__)


# Although undocumented, gitlab.com has a limit on how many jobs
# can be displayed in a single stage. Gitlab is able to deal with
# many more jobs than this limit, it just doesn't display them.
#
# The issue was originally reported[1] and fixed by bumping the
# limit to 200[2]. That said, a later patch made this value configurable
# and it seems gitlab.com sticks with 100. As of this writing,
# the value is not documented[4].
#
# [1] https://gitlab.com/gitlab-org/gitlab/-/issues/336319
# [2] https://gitlab.com/gitlab-org/gitlab/-/merge_requests/69314
# [3] https://gitlab.com/gitlab-org/gitlab/-/merge_requests/69853
# [4] https://docs.gitlab.com/ee/user/gitlab_com/index.html#gitlabcom-specific-rate-limits  # noqa E501
_MAXIMUM_NUMBER_OF_DISPLAYED_JOBS_PER_STAGE = 100


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

    jobs_list = list(jobs())

    number_of_stages_to_generate = (
        len(jobs_list) // _MAXIMUM_NUMBER_OF_DISPLAYED_JOBS_PER_STAGE
    ) + 1

    if number_of_stages_to_generate > 1:
        logger.info(
            f"Stage {stage} has more than {_MAXIMUM_NUMBER_OF_DISPLAYED_JOBS_PER_STAGE}"
            f" jobs. Splitting stage into {number_of_stages_to_generate}..."
        )

    for chunk in range(1, number_of_stages_to_generate + 1):
        stage_name = stage if number_of_stages_to_generate == 1 else f"{stage}_{chunk}"
        jobs_in_chunk = chunkify(jobs_list, chunk, number_of_stages_to_generate)

        for name, job in jobs_in_chunk:
            job["name"] = name
            job["stage"] = stage_name
            set_cache_upstream_jobs(job, loaded_jobs)
            logger.debug(f"Generating jobs for {stage_name} {name}")
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
