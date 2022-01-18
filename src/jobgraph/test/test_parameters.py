import pytest

from jobgraph import parameters
from jobgraph.test.conftest import FakeRepo

from .mockedopen import MockedOpen


@pytest.fixture
def vals():
    return {
        "base_repository": "repository",
        "base_rev": "baserev",
        "build_date": 0,
        "do_not_optimize": [],
        "filters": ["target_jobs_method"],
        "head_ref": "ref",
        "head_ref_protection": "protected",
        "head_repository": "repository",
        "head_rev": "rev",
        "head_tag": "",
        "optimize_target_jobs": True,
        "owner": "nobody@mozilla.com",
        "target_jobs_method": "default",
        "pipeline_id": 1234,
        "pipeline_source": "push",
    }


@pytest.fixture
def repo_mock(monkeypatch):
    monkeypatch.setattr(
        parameters,
        "get_repo",
        lambda *args, **kwargs: FakeRepo(),
    )


def test_Parameters_immutable(repo_mock, vals):
    p = parameters.Parameters(**vals)

    with pytest.raises(Exception):
        p["owner"] = "nobody@example.test"


def test_Parameters_missing_KeyError(repo_mock, vals):
    p = parameters.Parameters(**vals)
    with pytest.raises(KeyError):
        p["z"]


def test_Parameters_invalid_KeyError(repo_mock, vals):
    """even if the value is present, if it's not a valid property, raise KeyError"""
    p = parameters.Parameters(xyz=10, strict=True, **vals)
    with pytest.raises(parameters.ParameterMismatch):
        p.check()


def test_Parameters_get(repo_mock, vals):
    p = parameters.Parameters(owner="nobody@example.test")
    assert p["owner"] == "nobody@example.test"


def test_Parameters_check(repo_mock, vals):
    p = parameters.Parameters(**vals)
    p.check()  # should not raise


def test_Parameters_check_missing(repo_mock, vals):
    p = parameters.Parameters()
    with pytest.raises(parameters.ParameterMismatch):
        p.check()

    p = parameters.Parameters(strict=False)
    p.check()  # should not raise


def test_Parameters_check_extra(repo_mock, vals):
    p = parameters.Parameters(xyz=10, **vals)
    with pytest.raises(parameters.ParameterMismatch):
        p.check()

    p = parameters.Parameters(strict=False, xyz=10, **vals)
    p.check()  # should not raise


def test_Parameters_file_url_git_remote(repo_mock, vals):
    vals = vals.copy()
    vals["head_repository"] = "git@bitbucket.com:owner/repo.git"
    p = parameters.Parameters(**vals)
    with pytest.raises(parameters.ParameterMismatch):
        p.file_url("")

    vals["head_repository"] = "git@github.com:owner/repo.git"
    p = parameters.Parameters(**vals)
    assert p.file_url("", pretty=True).startswith("https://github.com/owner/repo/blob/")

    vals["head_repository"] = "https://github.com/mozilla-mobile/reference-browser"
    p = parameters.Parameters(**vals)
    assert p.file_url("", pretty=True).startswith(
        "https://github.com/mozilla-mobile/reference-browser/blob/"
    )

    vals["head_repository"] = "https://github.com/mozilla-mobile/reference-browser/"
    p = parameters.Parameters(**vals)
    assert p.file_url("", pretty=True).startswith(
        "https://github.com/mozilla-mobile/reference-browser/blob/"
    )


def test_load_parameters_file_yaml(repo_mock, vals):
    with MockedOpen({"params.yml": "some: data\n"}):
        assert parameters.load_parameters_file("params.yml") == {"some": "data"}


def test_load_parameters_file_json(repo_mock, vals):
    with MockedOpen({"params.json": '{"some": "data"}'}):
        assert parameters.load_parameters_file("params.json") == {"some": "data"}


def test_load_parameters_override(repo_mock, vals):
    """
    When ``load_parameters_file`` is passed overrides, they are included in
    the generated parameters.
    """
    assert parameters.load_parameters_file("", overrides={"some": "data"}) == {
        "some": "data"
    }


def test_load_parameters_override_file(repo_mock, vals):
    """
    When ``load_parameters_file`` is passed overrides, they overwrite data
    loaded from a file.
    """
    with MockedOpen({"params.json": '{"some": "data"}'}):
        assert parameters.load_parameters_file(
            "params.json", overrides={"some": "other"}
        ) == {"some": "other"}


def test_parameters_id(repo_mock):
    # Some parameters rely on current time, ensure these are the same for the
    # purposes of this test.
    defaults = {
        "build_date": 0,
    }

    params1 = parameters.Parameters(strict=False, spec=None, foo="bar", **defaults)
    assert params1.id
    assert len(params1.id) == 12

    params2 = parameters.Parameters(strict=False, spec="p2", foo="bar", **defaults)
    assert params1.id == params2.id

    params3 = parameters.Parameters(strict=False, spec="p3", foo="baz", **defaults)
    assert params1.id != params3.id


@pytest.mark.parametrize(
    "spec,expected",
    (
        (None, "defaults"),
        ("foo/bar.yaml", "bar"),
        ("foo/bar.yml", "bar"),
        ("/bar.json", "bar"),
        ("http://example.org/bar.yml?id=0", "bar"),
        ("task-id=123", "task-id=123"),
    ),
)
def test_parameters_format_spec(spec, expected):
    assert parameters.Parameters.format_spec(spec) == expected
