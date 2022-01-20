import pytest

from jobgraph.graph import Graph
from jobgraph.util.order_stages import order_stages


@pytest.mark.parametrize(
    "graph, all_jobs_per_label, expected_stages",
    (
        (
            Graph({"job_a1", "job_b1"}, {("job_b1", "job_a1", "b1 depends on a1")}),
            {
                "job_a1": {"stage": "stage_a"},
                "job_b1": {"stage": "stage_b"},
            },
            ["stage_a", "stage_b"],
        ),
        (
            Graph({"job_a1", "job_a2"}, {("job_a2", "job_a1", "a2 depends on a1")}),
            {
                "job_a1": {"stage": "stage_a"},
                "job_a2": {"stage": "stage_a"},
            },
            ["stage_a"],
        ),
        (
            Graph(
                {"job_a1", "job_b1", "job_b2"},
                {
                    ("job_b1", "job_a1", "b1 depends on a1"),
                },
            ),
            {
                "job_a1": {"stage": "stage_a"},
                "job_b1": {"stage": "stage_b"},
                "job_b2": {"stage": "stage_b"},
            },
            ["stage_a", "stage_b"],
        ),
        (
            Graph(
                {"job_a", "job_b1", "job_b2", "job_c1", "job_c2"},
                {
                    ("job_c1", "job_a", "c1 depends on a"),
                    ("job_c2", "job_b2", "c2 depends on b2"),
                },
            ),
            {
                "job_a": {"stage": "stage_a"},
                "job_b1": {"stage": "stage_b"},
                "job_b2": {"stage": "stage_b"},
                "job_c1": {"stage": "stage_c"},
                "job_c2": {"stage": "stage_c"},
            },
            ["stage_a", "stage_b", "stage_c"],
        ),
    ),
)
def test_order_stages(graph, all_jobs_per_label, expected_stages):
    assert order_stages(graph, all_jobs_per_label) == expected_stages
