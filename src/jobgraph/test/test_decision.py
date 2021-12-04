import json
import os
import shutil
import tempfile
import unittest
from copy import copy

import pytest

from jobgraph import decision
from jobgraph import parameters as jg_parameters
from jobgraph.test.conftest import FakeRepo
from jobgraph.util.yaml import load_yaml

FAKE_GRAPH_CONFIG = {"product-dir": "browser", "jobgraph": {}}


class TestDecision(unittest.TestCase):
    def test_write_artifact_json(self):
        data = [{"some": "data"}]
        tmpdir = tempfile.mkdtemp()
        try:
            decision.ARTIFACTS_DIR = os.path.join(tmpdir, "artifacts")
            decision.write_artifact("artifact.json", data)
            with open(os.path.join(decision.ARTIFACTS_DIR, "artifact.json")) as f:
                self.assertEqual(json.load(f), data)
        finally:
            if os.path.exists(tmpdir):
                shutil.rmtree(tmpdir)
            decision.ARTIFACTS_DIR = "artifacts"

    def test_write_artifact_yml(self):
        data = [{"some": "data"}]
        tmpdir = tempfile.mkdtemp()
        try:
            decision.ARTIFACTS_DIR = os.path.join(tmpdir, "artifacts")
            decision.write_artifact("artifact.yml", data)
            self.assertEqual(load_yaml(decision.ARTIFACTS_DIR, "artifact.yml"), data)
        finally:
            if os.path.exists(tmpdir):
                shutil.rmtree(tmpdir)
            decision.ARTIFACTS_DIR = "artifacts"


@pytest.fixture
def repo_mock(monkeypatch):
    monkeypatch.setattr(
        jg_parameters,
        "get_repo",
        lambda *args, **kwargs: FakeRepo(),
    )


DEFAULT_OPTIONS = {
    "base_repository": "https://gitlab.com/some-user/some-project",
    "base_rev": "0123",
    "head_repository": "https://gitlab.com/some-other-user/some-project",
    "head_rev": "abcd",
    "head_ref": "ef01",
    "head_ref_protection": "protected",
    "head_tag": "v0.0.1",
    "owner": "nobody@mozilla.com",
    "pipeline_source": "push",
}


def test_simple_options(repo_mock):
    params = decision.get_decision_parameters(FAKE_GRAPH_CONFIG, DEFAULT_OPTIONS)
    # TODO: Use freezegun to get a reproductible test on build_date
    # self.assertEqual(params["build_date"], 1503691511)
    assert params["head_tag"] == "v0.0.1"


def test_no_email_owner(repo_mock):
    options = copy(DEFAULT_OPTIONS)
    options["owner"] = "ffxbld"
    params = decision.get_decision_parameters(FAKE_GRAPH_CONFIG, options)
    assert params["owner"] == "ffxbld@noreply.mozilla.org"
