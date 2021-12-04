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
    - upstream_dependencies: jobs this one depends on, in the form {name: label},
      for example {'build': 'build-linux64/opt', 'docker_image': 'desktop_test'}

    And later, as the task-graph processing proceeds:

    This class is just a convenience wrapper for the data type and managing
    display, comparison, serialization, etc. It has no functionality of its own.
    """

    stage = attr.ib()
    label = attr.ib()
    description = attr.ib()
    attributes = attr.ib()
    actual_gitlab_ci_job = attr.ib()
    optimization = attr.ib(default=None)
    upstream_dependencies = attr.ib(factory=dict)

    def __attrs_post_init__(self):
        self.attributes["stage"] = self.stage

    def to_json(self):
        rv = {
            "stage": self.stage,
            "label": self.label,
            "description": self.description,
            "attributes": self.attributes,
            "upstream_dependencies": self.upstream_dependencies,
            "optimization": self.optimization,
            "actual_gitlab_ci_job": self.actual_gitlab_ci_job,
        }
        return rv

    @classmethod
    def from_json(cls, job_dict):
        """
        Given a data structure as produced by jobgraph.to_json, re-construct
        the original Task object.  This is used to "resume" the task-graph
        generation process, for example in Action jobs.
        """
        rv = cls(
            stage=job_dict["stage"],
            label=job_dict["label"],
            description=job_dict["description"],
            attributes=job_dict["attributes"],
            actual_gitlab_ci_job=job_dict["actual_gitlab_ci_job"],
            optimization=job_dict["optimization"],
            upstream_dependencies=job_dict.get("upstream_dependencies"),
        )
        return rv
