from jobgraph.target_jobs import target_jobs


# Define a custom target graph this way. Useful to target specific jobs on a schedule.
@target_jobs("single_job_on_given_schedule")
def target_jobs_some_schedule(full_job_graph, parameters, graph_config):
    # Use job attributes to select what jobs should be in the target graph.
    def filter(job, parameters):
        return job.attributes.get("single_job_on_given_schedule", False)

    return [l for l, t in full_job_graph.jobs.items() if filter(t, parameters)]
