# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import attr


@attr.s
class Job:
    """
    Representation of a job in a JobGraph.  Each Job has, at creation:

    - stage: the name of the task stage
    - label; the label for this task
    - attributes: a dictionary of attributes for this task (used for filtering)
    - actual_gitlab_ci_job: the job definition (JSON-able dictionary) which
      will be output to `.gitlab-ci.yml`
    - optimization: optimization to apply to the task (see jobgraph.optimize)
    - dependencies: tasks this one depends on, in the form {name: label}, for example
      {'build': 'build-linux64/opt', 'docker-image': 'build-docker-image-desktop-test'}

    And later, as the task-graph processing proceeds:

    - task_id -- TaskCluster taskId under which this task will be created

    This class is just a convenience wrapper for the data type and managing
    display, comparison, serialization, etc. It has no functionality of its own.
    """

    stage = attr.ib()
    label = attr.ib()
    description = attr.ib()
    attributes = attr.ib()
    actual_gitlab_ci_job = attr.ib()
    task_id = attr.ib(default=None, init=False)
    optimization = attr.ib(default=None)
    dependencies = attr.ib(factory=dict)

    def __attrs_post_init__(self):
        self.attributes["stage"] = self.stage

    def to_json(self):
        rv = {
            "stage": self.stage,
            "label": self.label,
            "description": self.description,
            "attributes": self.attributes,
            "dependencies": self.dependencies,
            "optimization": self.optimization,
            "actual_gitlab_ci_job": self.actual_gitlab_ci_job,
        }
        if self.task_id:
            rv["task_id"] = self.task_id
        return rv

    @classmethod
    def from_json(cls, job_dict):
        """
        Given a data structure as produced by jobgraph.to_json, re-construct
        the original Task object.  This is used to "resume" the task-graph
        generation process, for example in Action tasks.
        """
        rv = cls(
            stage=job_dict["stage"],
            label=job_dict["label"],
            description=job_dict["description"],
            attributes=job_dict["attributes"],
            actual_gitlab_ci_job=job_dict["actual_gitlab_ci_job"],
            optimization=job_dict["optimization"],
            dependencies=job_dict.get("dependencies"),
        )
        if "task_id" in job_dict:
            rv.task_id = job_dict["task_id"]
        return rv
