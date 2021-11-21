# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from jobgraph import graph

from .conftest import FakeKind


def test_stage_ordering(maketgg):
    "When task stages depend on each other, they are loaded in postorder"
    tgg = maketgg(
        stages=[
            ("_fake3", {"stage-dependencies": ["_fake2", "_fake1"]}),
            ("_fake2", {"stage-dependencies": ["_fake1"]}),
            ("_fake1", {"stage-dependencies": []}),
        ]
    )
    tgg._run_until("full_job_set")
    assert FakeKind.loaded_stages == ["_fake1", "_fake2", "_fake3"]


def test_full_job_set(maketgg):
    "The full_job_set property has all tasks"
    tgg = maketgg()
    assert tgg.full_job_set.graph == graph.Graph(
        {"_fake-t-0", "_fake-t-1", "_fake-t-2"}, set()
    )
    assert sorted(tgg.full_job_set.jobs.keys()) == sorted(
        ["_fake-t-0", "_fake-t-1", "_fake-t-2"]
    )


def test_full_job_graph(maketgg):
    "The full_job_graph property has all tasks, and links"
    tgg = maketgg()
    assert tgg.full_job_graph.graph == graph.Graph(
        {"_fake-t-0", "_fake-t-1", "_fake-t-2"},
        {
            ("_fake-t-1", "_fake-t-0", "prev"),
            ("_fake-t-2", "_fake-t-1", "prev"),
        },
    )
    assert sorted(tgg.full_job_graph.jobs.keys()) == sorted(
        ["_fake-t-0", "_fake-t-1", "_fake-t-2"]
    )


def test_target_job_set(maketgg):
    "The target_job_set property has the targeted tasks"
    tgg = maketgg(["_fake-t-1"])
    assert tgg.target_job_set.graph == graph.Graph({"_fake-t-1"}, set())
    assert set(tgg.target_job_set.jobs.keys()) == {"_fake-t-1"}


def test_target_job_graph(maketgg):
    "The target_job_graph property has the targeted tasks and deps"
    tgg = maketgg(["_fake-t-1"])
    assert tgg.target_job_graph.graph == graph.Graph(
        {"_fake-t-0", "_fake-t-1"}, {("_fake-t-1", "_fake-t-0", "prev")}
    )
    assert sorted(tgg.target_job_graph.jobs.keys()) == sorted(
        ["_fake-t-0", "_fake-t-1"]
    )


def test_always_target_jobs(maketgg):
    "The target_job_graph includes tasks with 'always_target'"
    tgg_args = {
        "target_jobs": ["_fake-t-0", "_fake-t-1", "_ignore-t-0", "_ignore-t-1"],
        "stages": [
            ("_fake", {"job_defaults": {"optimization": {"odd": None}}}),
            (
                "_ignore",
                {
                    "job_defaults": {
                        "attributes": {"always_target": True},
                        "optimization": {"always": True},
                    }
                },
            ),
        ],
        "params": {"optimize_target_jobs": False},
    }
    tgg = maketgg(**tgg_args)
    assert sorted(tgg.target_job_set.jobs.keys()) == sorted(
        ["_fake-t-0", "_fake-t-1", "_ignore-t-0", "_ignore-t-1"]
    )
    assert sorted(tgg.target_job_graph.jobs.keys()) == sorted(
        ["_fake-t-0", "_fake-t-1", "_ignore-t-0", "_ignore-t-1", "_ignore-t-2"]
    )
    assert sorted(t.label for t in tgg.optimized_job_graph.jobs.values()) == sorted(
        ["_fake-t-0", "_fake-t-1", "_ignore-t-0", "_ignore-t-1", "_ignore-t-2"]
    )


def test_optimized_job_graph(maketgg):
    "The optimized task graph contains task ids"
    tgg = maketgg(["_fake-t-2"])
    assert tgg.optimized_job_graph.graph == graph.Graph(
        {"_fake-t-0", "_fake-t-1", "_fake-t-2"},
        {
            ("_fake-t-1", "_fake-t-0", "prev"),
            ("_fake-t-2", "_fake-t-1", "prev"),
        },
    )
