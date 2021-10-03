# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


from .graph import Graph
from .job import Job

import attr


@attr.s(frozen=True)
class JobGraph:
    """
    Representation of a job graph.

    A job graph is a combination of a Graph and a dictionary of jobs indexed
    by label. JobGraph instances should be treated as immutable.
    """

    jobs = attr.ib()
    graph = attr.ib()

    def __attrs_post_init__(self):
        assert set(self.jobs) == self.graph.nodes

    def for_each_job(self, f, *args, **kwargs):
        for job_label in self.graph.visit_postorder():
            job = self.jobs[job_label]
            f(job, self, *args, **kwargs)

    def __getitem__(self, label):
        "Get a job by label"
        return self.jobs[label]

    def __contains__(self, label):
        return label in self.jobs

    def __iter__(self):
        "Iterate over jobs in undefined order"
        return iter(self.jobs.values())

    def to_json(self):
        "Return a JSON-able object representing the job graph, as documented"
        named_links_dict = self.graph.named_links_dict()
        # this dictionary may be keyed by label or by taskid, so let's just call it 'key'
        jobs = {}
        for key in self.graph.visit_postorder():
            jobs[key] = self.jobs[key].to_json()
            # overwrite dependencies with the information in the jobgraph's edges.
            jobs[key]["dependencies"] = named_links_dict.get(key, {})
        return jobs

    @classmethod
    def from_json(cls, jobs_dict):
        """
        This code is used to generate the a JobGraph using a dictionary
        which is representative of the JobGraph.
        """
        jobs = {}
        edges = set()
        for key, value in jobs_dict.items():
            jobs[key] = Job.from_json(value)
            if "task_id" in value:
                jobs[key].task_id = value["task_id"]
            for depname, dep in value["dependencies"].items():
                edges.add((key, dep, depname))
        job_graph = cls(jobs, Graph(set(jobs), edges))
        return jobs, job_graph
