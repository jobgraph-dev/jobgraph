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


def resolve_task_references(label, task_def, dependencies, docker_images):
    """Resolve all instances of
      {'docker-image-reference': '..<..>..'}
    in the given task definition, using the given dependencies"""

    def docker_image_reference(val):
        def repl(match):
            key = match.group(1)
            try:
                docker_image = docker_images[key]
                return docker_image
            except KeyError:
                # handle escaping '<'
                if key == "<":
                    return key
                raise KeyError(f"task '{label}' has no dependency named '{key}'")

        return DOCKER_IMAGE_REFERENCE_PATTERN.sub(repl, val)

    return _recurse(
        task_def,
        {
            "docker-image-reference": docker_image_reference,
        },
    )
