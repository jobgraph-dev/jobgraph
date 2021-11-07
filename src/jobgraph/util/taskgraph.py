# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Tools for interacting with existing jobgraphs.
"""


def find_decision_task(parameters, graph_config):
    """Given the parameters for this action, find the taskId of the decision
    task"""
    # TODO: Use Gitlab API to find decision job ID
    raise NotImplementedError(
        "Please implement a way to find the decision job on Gitlab CI!"
    )
