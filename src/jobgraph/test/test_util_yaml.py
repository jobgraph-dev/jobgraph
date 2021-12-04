import unittest

from jobgraph.util import yaml

from .mockedopen import MockedOpen

FOO_YML = """\
prop:
    - val1
"""


class TestYaml(unittest.TestCase):
    def test_load(self):
        with MockedOpen({"/dir1/dir2/foo.yml": FOO_YML}):
            self.assertEqual(
                yaml.load_yaml("/dir1/dir2", "foo.yml"), {"prop": ["val1"]}
            )
