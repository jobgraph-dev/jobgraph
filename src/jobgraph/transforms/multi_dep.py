from jobgraph.transforms.base import TransformSequence

transforms = TransformSequence()


@transforms.add
def build_name_attributes_and_dependencies(config, jobs):
    for job in jobs:
        primary_dependency = job.pop("primary_dependency")
        dependent_jobs = job.pop("dependent_jobs", [primary_dependency])

        job["upstream_dependencies"] = {
            dep.stage: dep.label for dep in dependent_jobs.values()
        }

        stage_cache_dependencies = config.config.get("stage_cache_dependencies", [])
        if stage_cache_dependencies:
            job["upstream_cache_jobs"] = [
                dep
                for dep in dependent_jobs.values()
                if dep.stage in stage_cache_dependencies
            ]

        copy_of_attributes = primary_dependency.attributes.copy()
        job.setdefault("attributes", copy_of_attributes)
        job["name"] = _build_job_name(config.stage, primary_dependency)

        yield job


def _build_job_name(stage, dependent_job):
    if dependent_job.label.endswith(dependent_job.stage):
        stage_length = len(dependent_job.stage) + 1
        dependent_job_name = dependent_job.label[:-stage_length]
    else:
        dependent_job_name = dependent_job.label

    return f"{dependent_job_name}_{stage}"
