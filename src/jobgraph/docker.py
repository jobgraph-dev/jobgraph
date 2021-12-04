import os

from jobgraph.util.docker_registries import fetch_image_digest_from_registry, set_digest
from jobgraph.util.memoize import memoize


def get_docker_image_job(image_name, root_dir=None):
    jobs = _load_all_docker_image_jobs(root_dir)
    return jobs[image_name]


@memoize
def _load_all_docker_image_jobs(root_dir):
    from jobgraph.generator import load_jobs_for_stage
    from jobgraph.parameters import Parameters

    params = Parameters(
        repo_dir=os.path.dirname(root_dir) if root_dir else None,
        head_ref_protection="protected",
        strict=False,
    )
    return load_jobs_for_stage(params, "docker_image", root_dir=root_dir)


def get_image_context_hash(image_name, root_dir=None):
    job = get_docker_image_job(image_name, root_dir)
    return job.attributes["context_hash"]


def get_image_full_location(image_name, root_dir=None):
    job = get_docker_image_job(image_name, root_dir)
    return job.attributes["docker_image_full_location"]


def get_image_full_location_with_digest(image_name, root_dir=None):
    image_full_location = get_image_full_location(image_name, root_dir)
    digest = fetch_image_digest_from_registry(image_full_location)
    return set_digest(image_full_location, digest)
