import pytest

from jobgraph import generator
from jobgraph import target_jobs as target_jobs_mod
from jobgraph.config import GraphConfig
from jobgraph.generator import JobGraphGenerator, Stage
from jobgraph.optimize import OptimizationStrategy
from jobgraph.util.templates import merge


def fake_loader(stage, path, config, parameters, loaded_jobs):
    for i in range(3):
        dependencies = {}
        if i >= 1:
            dependencies["prev"] = f"{stage}-t-{i - 1}"

        task = {
            "stage": stage,
            "label": f"{stage}-t-{i}",
            "description": f"{stage} task {i}",
            "attributes": {"_tasknum": str(i)},
            "actual_gitlab_ci_job": {
                "i": i,
                "metadata": {"name": f"t-{i}"},
                "deadline": "soon",
            },
            "dependencies": dependencies,
        }
        if "job-defaults" in config:
            task = merge(config["job-defaults"], task)
        yield task


class FakeKind(Stage):
    def _get_loader(self):
        return fake_loader

    def load_jobs(self, parameters, loaded_jobs, write_artifacts):
        FakeKind.loaded_stages.append(self.name)
        return super().load_jobs(parameters, loaded_jobs, write_artifacts)


class WithFakeKind(JobGraphGenerator):
    def _load_stages(self, graph_config, target_stage=None):
        for stage_name, cfg in self.parameters["_stages"]:
            config = {
                "transforms": [],
            }
            if cfg:
                config.update(cfg)
            yield FakeKind(stage_name, "/fake", config, graph_config)


def fake_load_graph_config(root_dir):
    graph_config = GraphConfig(
        {"docker": {"docker-in-docker": "some:dind@sha256:deadbeef"}, "jobgraph": {}},
        root_dir,
    )
    graph_config.__dict__["register"] = lambda: None
    return graph_config


class FakeParameters(dict):
    strict = True


class FakeOptimization(OptimizationStrategy):
    def __init__(self, mode, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode

    def should_remove_job(self, task, params, arg):
        if self.mode == "always":
            return True
        if self.mode == "even":
            return task.actual_gitlab_ci_job["i"] % 2 == 0
        if self.mode == "odd":
            return task.actual_gitlab_ci_job["i"] % 2 != 0
        return False


@pytest.fixture
def maketgg(monkeypatch):
    def inner(target_jobs=None, stages=[("_fake", [])], params=None):
        params = params or {}
        FakeKind.loaded_stages = []
        target_jobs = target_jobs or []

        def target_jobs_method(full_job_graph, parameters, graph_config):
            return target_jobs

        target_jobs_mod._target_task_methods["test_method"] = target_jobs_method

        parameters = FakeParameters(
            {
                "_stages": stages,
                "target_jobs_method": "test_method",
                "try_mode": None,
                "pipeline_source": "push",
            }
        )
        parameters.update(params)

        monkeypatch.setattr(generator, "load_graph_config", fake_load_graph_config)

        return WithFakeKind("/root", parameters)

    return inner
