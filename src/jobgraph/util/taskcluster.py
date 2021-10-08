# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import os
import datetime
import functools
import requests
import logging
import taskcluster_urls as liburls
from requests.packages.urllib3.util.retry import Retry
from jobgraph.job import Job
from jobgraph.util.memoize import memoize
from jobgraph.util import yaml

logger = logging.getLogger(__name__)

# Default rootUrl to use if none is given in the environment; this should point
# to the production Taskcluster deployment used for CI.
PRODUCTION_TASKCLUSTER_ROOT_URL = "https://taskcluster.net"

# the maximum number of parallel Taskcluster API calls to make
CONCURRENCY = 50

# the maximum number of parallel Taskcluster API calls to make
CONCURRENCY = 50


@memoize
def get_root_url():
    """Get the current TASKCLUSTER_ROOT_URL.  When running in a task, this must
    come from $TASKCLUSTER_ROOT_URL; when run on the command line, we apply a
    defualt that points to the production deployment of Taskcluster. """
    if "TASKCLUSTER_ROOT_URL" not in os.environ:
        if "TASK_ID" in os.environ:
            raise RuntimeError(
                "$TASKCLUSTER_ROOT_URL must be set when running in a task"
            )
        else:
            logger.debug("Using default TASKCLUSTER_ROOT_URL (Firefox CI production)")
            return PRODUCTION_TASKCLUSTER_ROOT_URL
    logger.debug(
        "Running in Taskcluster instance {}".format(
            os.environ["TASKCLUSTER_ROOT_URL"],
        )
    )
    return os.environ["TASKCLUSTER_ROOT_URL"]


@memoize
def get_session():
    session = requests.Session()

    retry = Retry(total=5, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])

    # Default HTTPAdapter uses 10 connections. Mount custom adapter to increase
    # that limit. Connections are established as needed, so using a large value
    # should not negatively impact performance.
    http_adapter = requests.adapters.HTTPAdapter(
        pool_connections=CONCURRENCY, pool_maxsize=CONCURRENCY, max_retries=retry
    )
    session.mount("https://", http_adapter)
    session.mount("http://", http_adapter)

    return session


def _do_request(url, force_get=False, **kwargs):
    session = get_session()
    if kwargs and not force_get:
        response = session.post(url, **kwargs)
    else:
        response = session.get(url, stream=True, **kwargs)
    if response.status_code >= 400:
        # Consume content before raise_for_status, so that the connection can be
        # reused.
        response.content
    response.raise_for_status()
    return response


def _handle_artifact(path, response):
    if path.endswith(".json"):
        return response.json()
    if path.endswith(".yml"):
        return yaml.load_stream(response.text)
    response.raw.read = functools.partial(response.raw.read, decode_content=True)
    return response.raw


def get_artifact_url(task_id, path):
    artifact_tmpl = liburls.api(
        get_root_url(False), "queue", "v1", "task/{}/artifacts/{}"
    )
    data = artifact_tmpl.format(task_id, path)
    return data


def get_artifact(task_id, path):
    """
    Returns the artifact with the given path for the given task id.

    If the path ends with ".json" or ".yml", the content is deserialized as,
    respectively, json or yaml, and the corresponding python data (usually
    dict) is returned.
    For other types of content, a file-like object is returned.
    """
    response = _do_request(get_artifact_url(task_id, path))
    return _handle_artifact(path, response)


def list_artifacts(task_id):
    response = _do_request(get_artifact_url(task_id, "").rstrip("/"))
    return response.json()["artifacts"]


def get_artifact_prefix(task):
    prefix = None
    if isinstance(task, dict):
        prefix = task.get("attributes", {}).get("artifact_prefix")
    elif isinstance(task, Job):
        prefix = task.attributes.get("artifact_prefix")
    else:
        raise Exception(f"Can't find artifact-prefix of non-task: {task}")
    return prefix or "public/build"


def get_artifact_path(task, path):
    return f"{get_artifact_prefix(task)}/{path}"


def parse_time(timestamp):
    """Turn a "JSON timestamp" as used in TC APIs into a datetime"""
    return datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")


def get_task_url(task_id):
    task_tmpl = liburls.api(get_root_url(), "queue", "v1", "task/{}")
    return task_tmpl.format(task_id)


def get_task_definition(task_id):
    response = _do_request(get_task_url(task_id))
    return response.json()


def cancel_task(task_id):
    """Cancels a task given a task_id. In testing mode, just logs that it would
    have cancelled."""
    _do_request(get_task_url(task_id) + "/cancel", json={})


def status_task(task_id):
    """Gets the status of a task given a task_id. In testing mode, just logs that it would
    have retrieved status."""
    resp = _do_request(get_task_url(task_id) + "/status")
    status = resp.json().get("status", {}).get("state") or "unknown"
    return status


def rerun_task(task_id):
    """Reruns a task given a task_id. In testing mode, just logs that it would
    have reran."""
    _do_request(get_task_url(task_id) + "/rerun", json={})


def get_purge_cache_url(worker_type):
    url_tmpl = liburls.api(
        get_root_url(), "purge-cache", "v1", "purge-cache/{}/{}"
    )
    return url_tmpl.format(worker_type)


def purge_cache(worker_type, cache_name):
    """Requests a cache purge from the purge-caches service."""
    logger.info(f"Purging {worker_type}/{cache_name}.")
    purge_cache_url = get_purge_cache_url(worker_type)
    _do_request(purge_cache_url, json={"cacheName": cache_name})


def send_email(address, subject, content, link):
    """Sends an email using the notify service"""
    logger.info(f"Sending email to {address}.")
    url = liburls.api(get_root_url(), "notify", "v1", "email")
    _do_request(
        url,
        json={
            "address": address,
            "subject": subject,
            "content": content,
            "link": link,
        },
    )


def list_task_group_incomplete_tasks(task_group_id):
    """Generate the incomplete tasks in a task group"""
    params = {}
    while True:
        url = liburls.api(
            get_root_url(False),
            "queue",
            "v1",
            f"task-group/{task_group_id}/list",
        )
        resp = _do_request(url, force_get=True, params=params).json()
        for task in [t["status"] for t in resp["tasks"]]:
            if task["state"] in ["running", "pending", "unscheduled"]:
                yield task["taskId"]
        if resp.get("continuationToken"):
            params = {"continuationToken": resp.get("continuationToken")}
        else:
            break
