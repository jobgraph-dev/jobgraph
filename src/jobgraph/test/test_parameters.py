# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import unittest

import pytest

from jobgraph.parameters import (
    Parameters,
    ParameterMismatch,
    load_parameters_file,
)

from .mockedopen import MockedOpen


class TestParameters(unittest.TestCase):

    vals = {
        "base_repository": "repository",
        "base_rev": "baserev",
        "build_date": 0,
        "do_not_optimize": [],
        "existing_tasks": {},
        "filters": ["target_jobs_method"],
        "head_ref": "ref",
        "head_repository": "repository",
        "head_rev": "rev",
        "head_tag": "",
        "level": "3",
        "optimize_target_jobs": True,
        "owner": "nobody@mozilla.com",
        "project": "project",
        "pushdate": 0,
        "target_jobs_method": "default",
        "pipeline_source": "push",
    }

    def test_Parameters_immutable(self):
        p = Parameters(**self.vals)

        def assign():
            p["owner"] = "nobody@example.test"

        self.assertRaises(Exception, assign)

    def test_Parameters_missing_KeyError(self):
        p = Parameters(**self.vals)
        self.assertRaises(KeyError, lambda: p["z"])

    def test_Parameters_invalid_KeyError(self):
        """even if the value is present, if it's not a valid property, raise KeyError"""
        p = Parameters(xyz=10, strict=True, **self.vals)
        self.assertRaises(ParameterMismatch, lambda: p.check())

    def test_Parameters_get(self):
        p = Parameters(owner="nobody@example.test", level=20)
        self.assertEqual(p["owner"], "nobody@example.test")

    def test_Parameters_check(self):
        p = Parameters(**self.vals)
        p.check()  # should not raise

    def test_Parameters_check_missing(self):
        p = Parameters()
        self.assertRaises(ParameterMismatch, lambda: p.check())

        p = Parameters(strict=False)
        p.check()  # should not raise

    def test_Parameters_check_extra(self):
        p = Parameters(xyz=10, **self.vals)
        self.assertRaises(ParameterMismatch, lambda: p.check())

        p = Parameters(strict=False, xyz=10, **self.vals)
        p.check()  # should not raise

    def test_Parameters_file_url_git_remote(self):
        vals = self.vals.copy()
        vals["head_repository"] = "git@bitbucket.com:owner/repo.git"
        p = Parameters(**vals)
        self.assertRaises(ParameterMismatch, lambda: p.file_url(""))

        vals["head_repository"] = "git@github.com:owner/repo.git"
        p = Parameters(**vals)
        self.assertTrue(
            p.file_url("", pretty=True).startswith(
                "https://github.com/owner/repo/blob/"
            )
        )

        vals["head_repository"] = "https://github.com/mozilla-mobile/reference-browser"
        p = Parameters(**vals)
        self.assertTrue(
            p.file_url("", pretty=True).startswith(
                "https://github.com/mozilla-mobile/reference-browser/blob/"
            )
        )

        vals["head_repository"] = "https://github.com/mozilla-mobile/reference-browser/"
        p = Parameters(**vals)
        self.assertTrue(
            p.file_url("", pretty=True).startswith(
                "https://github.com/mozilla-mobile/reference-browser/blob/"
            )
        )

    def test_load_parameters_file_yaml(self):
        with MockedOpen({"params.yml": "some: data\n"}):
            self.assertEqual(load_parameters_file("params.yml"), {"some": "data"})

    def test_load_parameters_file_json(self):
        with MockedOpen({"params.json": '{"some": "data"}'}):
            self.assertEqual(load_parameters_file("params.json"), {"some": "data"})

    def test_load_parameters_override(self):
        """
        When ``load_parameters_file`` is passed overrides, they are included in
        the generated parameters.
        """
        self.assertEqual(
            load_parameters_file("", overrides={"some": "data"}), {"some": "data"}
        )

    def test_load_parameters_override_file(self):
        """
        When ``load_parameters_file`` is passed overrides, they overwrite data
        loaded from a file.
        """
        with MockedOpen({"params.json": '{"some": "data"}'}):
            self.assertEqual(
                load_parameters_file("params.json", overrides={"some": "other"}),
                {"some": "other"},
            )


def test_parameters_id():
    # Some parameters rely on current time, ensure these are the same for the
    # purposes of this test.
    defaults = {
        "build_date": 0,
        "pushdate": 0,
    }

    params1 = Parameters(strict=False, spec=None, foo="bar", **defaults)
    assert params1.id
    assert len(params1.id) == 12

    params2 = Parameters(strict=False, spec="p2", foo="bar", **defaults)
    assert params1.id == params2.id

    params3 = Parameters(strict=False, spec="p3", foo="baz", **defaults)
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
        ("project=autoland", "project=autoland"),
    ),
)
def test_parameters_format_spec(spec, expected):
    assert Parameters.format_spec(spec) == expected
