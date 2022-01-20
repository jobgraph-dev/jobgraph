from jobgraph.graph import Graph


def order_stages(graph, all_actual_gitlab_ci_jobs_per_label):
    stages_nodes = set()
    stages_edges = set()

    for job_label, upstream_jobs_label in graph.links_dict().items():
        job = all_actual_gitlab_ci_jobs_per_label[job_label]
        current_stage = job["stage"]
        stages_nodes.add(current_stage)

        for upstream_job_label in upstream_jobs_label:
            upstream_job = all_actual_gitlab_ci_jobs_per_label[upstream_job_label]
            upstream_stage = upstream_job["stage"]
            stages_nodes.add(upstream_stage)

            if current_stage != upstream_stage:
                stages_edges.add(
                    (current_stage, upstream_stage, f"{current_stage}-{upstream_stage}")
                )

    stages_graph = Graph(stages_nodes, stages_edges)

    return list(stages_graph.visit_postorder())
