# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

import unittest

from taskgraph.parameters import (
    Parameters,
    ParameterMismatch,
    load_parameters_file,
    PARAMETERS,
)

from .mockedopen import MockedOpen


class TestParameters(unittest.TestCase):

    vals = {n: n for n in PARAMETERS.keys()}

    def test_Parameters_immutable(self):
        p = Parameters(**self.vals)

        def assign():
            p['owner'] = 'nobody@example.test'
        self.assertRaises(Exception, assign)

    def test_Parameters_missing_KeyError(self):
        p = Parameters(**self.vals)
        self.assertRaises(KeyError, lambda: p['z'])

    def test_Parameters_invalid_KeyError(self):
        """even if the value is present, if it's not a valid property, raise KeyError"""
        p = Parameters(xyz=10, **self.vals)
        self.assertRaises(KeyError, lambda: p['xyz'])

    def test_Parameters_get(self):
        p = Parameters(owner='nobody@example.test', level=20)
        self.assertEqual(p['owner'], 'nobody@example.test')

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

    def test_load_parameters_file_yaml(self):
        with MockedOpen({"params.yml": "some: data\n"}):
            self.assertEqual(
                    load_parameters_file('params.yml'),
                    {'some': 'data'})

    def test_load_parameters_file_json(self):
        with MockedOpen({"params.json": '{"some": "data"}'}):
            self.assertEqual(
                    load_parameters_file('params.json'),
                    {'some': 'data'})

    def test_load_parameters_override(self):
        """
        When ``load_parameters_file`` is passed overrides, they are included in
        the generated parameters.
        """
        self.assertEqual(
            load_parameters_file('', overrides={'some': 'data'}),
            {'some': 'data'})

    def test_load_parameters_override_file(self):
        """
        When ``load_parameters_file`` is passed overrides, they overwrite data
        loaded from a file.
        """
        with MockedOpen({"params.json": '{"some": "data"}'}):
            self.assertEqual(
                load_parameters_file('params.json', overrides={'some': 'other'}),
                {'some': 'other'})
