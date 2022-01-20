import attr

from .graph import Graph
from .job import Job
from .util.order_stages import order_stages


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
        # this dictionary may be keyed by label or by taskid, so let's just call
        # it 'key'
        jobs = {}
        for key in self.graph.visit_postorder():
            jobs[key] = self.jobs[key].to_json()
            # overwrite upstream_dependencies with the information in the
            # jobgraph's edges.
            jobs[key]["upstream_dependencies"] = named_links_dict.get(key, {})
        return jobs

    def to_gitlab_ci_jobs(self):
        all_jobs = {
            label: job.to_json()["actual_gitlab_ci_job"]
            for label, job in self.jobs.items()
        }
        return {
            "stages": order_stages(
                self.graph,
                all_actual_gitlab_ci_jobs_per_label=all_jobs,
            ),
            **all_jobs,
        }

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
            for depname, dep in value["upstream_dependencies"].items():
                edges.add((key, dep, depname))
        job_graph = cls(jobs, Graph(set(jobs), edges))
        return jobs, job_graph
