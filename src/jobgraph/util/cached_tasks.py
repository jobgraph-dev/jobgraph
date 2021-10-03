# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import hashlib
import time


def add_optimization(
    config, taskdesc, cache_type, cache_name, digest=None, digest_data=None
):
    """
    Allow the results of this task to be cached. This adds index routes to the
    task so it can be looked up for future runs, and optimization hints so that
    cached artifacts can be found. Exactly one of `digest` and `digest_data`
    must be passed.

    :param TransformConfig config: The configuration for the kind being transformed.
    :param dict taskdesc: The description of the current task.
    :param str cache_type: The type of task result being cached.
    :param str cache_name: The name of the object being cached.
    :param digest: A unique string indentifying this version of the artifacts
        being generated. Typically this will be the hash of inputs to the task.
    :type digest: bytes or None
    :param digest_data: A list of bytes representing the inputs of this task.
        They will be concatenated and hashed to create the digest for this
        task.
    :type digest_data: list of bytes or None
    """
    if (digest is None) == (digest_data is None):
        raise Exception("Must pass exactly one of `digest` and `digest_data`.")
    if digest is None:
        digest = hashlib.sha256("\n".join(digest_data).encode("utf-8")).hexdigest()

    if "cached-task-prefix" in config.graph_config["taskgraph"]:
        cache_prefix = config.graph_config["taskgraph"]["cached-task-prefix"]
    else:
        cache_prefix = config.graph_config["trust-domain"]

    subs = {
        "cache_prefix": cache_prefix,
        "type": cache_type,
        "name": cache_name,
        "digest": digest,
    }

    # We'll try to find a cached version of the toolchain at levels above and
    # including the current level, starting at the highest level.
    # Chain-of-trust doesn't handle tasks not built on the tip of a
    # pull-request, so don't look for level-1 tasks if building a pull-request.
    min_level = int(config.params["level"])
    if config.params["pipeline_source"] == "merge_request_event":
        min_level = max(min_level, 3)
    for level in reversed(range(min_level, 4)):
        subs["level"] = level

    # ... and cache at the lowest level.
    subs["level"] = config.params["level"]

    taskdesc["attributes"]["cached_task"] = {
        "type": cache_type,
        "name": cache_name,
        "digest": digest,
    }
