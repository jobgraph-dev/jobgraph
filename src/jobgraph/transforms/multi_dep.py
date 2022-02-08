from jobgraph.transforms.base import TransformSequence

transforms = TransformSequence()


@transforms.add
def build_name_and_attributes(config, jobs):
    for job in jobs:
        job["upstream_dependencies"] = {
            dep.stage: dep.label for dep in _get_all_deps(job)
        }
        primary_dep = job.pop("primary_dependency")
        copy_of_attributes = primary_dep.attributes.copy()
        job.setdefault("attributes", copy_of_attributes)
        job["name"] = _build_job_name(config.stage, primary_dep)

        yield job


def _build_job_name(stage, dependent_job):
    if dependent_job.label.endswith(dependent_job.stage):
        dependent_job_name = dependent_job.label[len(dependent_job.stage) + 1 :]
    else:
        dependent_job_name = dependent_job.label

    return f"{dependent_job_name}_{stage}"


def _get_all_deps(job):
    dependent_jobs = job.pop("dependent_jobs", None)
    if dependent_jobs:
        return dependent_jobs.values()

    return [job["primary_dependency"]]
