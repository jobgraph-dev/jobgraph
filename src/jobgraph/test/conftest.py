import pytest

from jobgraph import generator, optimize
from jobgraph import parameters as jg_parameters
from jobgraph import target_jobs as target_jobs_mod
from jobgraph.config import GraphConfig
from jobgraph.generator import JobGraphGenerator, Stage
from jobgraph.util.templates import merge


def fake_loader(stage, path, config, parameters, loaded_jobs):
    for i in range(3):
        upstream_dependencies = {}
        if i >= 1:
            upstream_dependencies["prev"] = f"{stage}-t-{i - 1}"

        task = {
            "stage": stage,
            "label": f"{stage}-t-{i}",
            "description": f"{stage} task {i}",
            "attributes": {"_tasknum": str(i)},
            "actual_gitlab_ci_job": {
                "image": f"image-{i}",
                "script": "some-script",
                "tags": ["some_runner_tag"],
            },
            "upstream_dependencies": upstream_dependencies,
        }
        if "job_defaults" in config:
            task = merge(config["job_defaults"], task)
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
        {"docker": {"docker_in_docker": "some:dind@sha256:deadbeef"}, "jobgraph": {}},
        root_dir,
    )
    graph_config.__dict__["register"] = lambda: None
    return graph_config


class FakeParameters(dict):
    strict = True


class FakeOptimization(optimize.OptimizationStrategy):
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


class FakeRepo:
    head_ref = "some_head_ref"

    def get_url(*args, **kwargs):
        return "some_url"

    def get_file_at_given_revision(*args, **kwargs):
        return "some_file_content"

    def does_commit_exist_locally(*args, **kwargs):
        return True


@pytest.fixture
def maketgg(monkeypatch):
    def inner(target_jobs=None, stages=[("_fake", [])], params=None):
        params = params or {}
        FakeKind.loaded_stages = []
        target_jobs = target_jobs or []

        def target_jobs_method(full_job_graph, parameters, graph_config):
            return target_jobs

        target_jobs_mod._target_jobs_methods["test_method"] = target_jobs_method

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
        monkeypatch.setattr(
            optimize,
            "_get_changed_external_docker_images",
            lambda *args, **kwargs: "",
        )

        monkeypatch.setattr(
            jg_parameters,
            "get_repo",
            lambda *args, **kwargs: FakeRepo(),
        )
        monkeypatch.setattr(
            optimize,
            "_remove_optimization_if_any_external_docker_image_has_changed",
            lambda *args, **kwargs: {},
        )

        return WithFakeKind("/root", parameters)

    return inner
