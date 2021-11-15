# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import re

from jobgraph.util.time import json_time_from_now

DOCKER_IMAGE_REFERENCE_PATTERN = re.compile("<([^>]+)>")


def _recurse(val, param_fns):
    def recurse(val):
        if isinstance(val, list):
            return [recurse(v) for v in val]
        elif isinstance(val, dict):
            if len(val) == 1:
                for param_key, param_fn in param_fns.items():
                    if set(val.keys()) == {param_key}:
                        return param_fn(val[param_key])
            return {k: recurse(v) for k, v in val.items()}
        else:
            return val

    return recurse(val)


def resolve_timestamps(now, task_def):
    """Resolve all instances of `{'relative-datestamp': '..'}` in the given task definition"""
    return _recurse(
        task_def,
        {
            "relative-datestamp": lambda v: json_time_from_now(v, now),
        },
    )


def resolve_docker_image_references(label, job_def, docker_images):
    """Resolve all instances of
      {'docker-image-reference': '..<..>..'}
    in the given task definition, using the given dependencies"""

    def docker_image_reference(val):
        def repl(match):
            image_reference = match.group(1)
            try:
                docker_image = docker_images[image_reference]
                return docker_image
            except KeyError:
                raise KeyError(
                    f'job "{label}" has no docker image named "{image_reference}"'
                )

        return DOCKER_IMAGE_REFERENCE_PATTERN.sub(repl, val)

    return _recurse(
        job_def,
        {
            "docker-image-reference": docker_image_reference,
        },
    )
