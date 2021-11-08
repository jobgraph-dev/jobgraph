# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import logging

from . import target_jobs

logger = logging.getLogger(__name__)

filter_job_functions = {}


def filter_job(name):
    """Generator to declare a task filter function."""

    def wrap(func):
        filter_job_functions[name] = func
        return func

    return wrap


@filter_job("target_jobs_method")
def filter_target_jobs(graph, parameters, graph_config):
    """Proxy filter to use legacy target tasks code.

    This should go away once target_jobs are converted to filters.
    """

    attr = parameters.get("target_jobs_method", "all_jobs")
    fn = target_jobs.get_method(attr)
    return fn(graph, parameters, graph_config)
