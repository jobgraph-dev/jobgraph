import unittest

from jobgraph.util.templates import merge, merge_to


class MergeTest(unittest.TestCase):
    def test_merge_to_dicts(self):
        source = {"a": 1, "b": 2}
        dest = {"b": "20", "c": 30}
        expected = {
            "a": 1,  # source only
            "b": 2,  # source overrides dest
            "c": 30,  # dest only
        }
        self.assertEqual(merge_to(source, dest), expected)
        self.assertEqual(dest, expected)

    def test_merge_to_lists(self):
        source = {"x": [3, 4]}
        dest = {"x": [1, 2]}
        expected = {"x": [1, 2, 3, 4]}  # dest first
        self.assertEqual(merge_to(source, dest), expected)
        self.assertEqual(dest, expected)

    def test_merge_diff_types(self):
        source = {"x": [1, 2]}
        dest = {"x": "abc"}
        expected = {"x": [1, 2]}  # source wins
        self.assertEqual(merge_to(source, dest), expected)
        self.assertEqual(dest, expected)

    def test_merge(self):
        first = {"a": 1, "b": 2, "d": 11}
        second = {"b": 20, "c": 30}
        third = {"c": 300, "d": 400}
        expected = {
            "a": 1,
            "b": 20,
            "c": 300,
            "d": 400,
        }
        self.assertEqual(merge(first, second, third), expected)

        # inputs haven't changed..
        self.assertEqual(first, {"a": 1, "b": 2, "d": 11})
        self.assertEqual(second, {"b": 20, "c": 30})
        self.assertEqual(third, {"c": 300, "d": 400})
