import datetime
import unittest

from jobgraph.util.parameterization import (
    resolve_docker_image_references,
    resolve_timestamps,
)


class TestTimestamps(unittest.TestCase):
    def test_no_change(self):
        now = datetime.datetime(2018, 1, 1)
        input = {
            "key": "value",
            "numeric": 10,
            "list": ["a", True, False, None],
        }
        self.assertEqual(resolve_timestamps(now, input), input)

    def test_buried_replacement(self):
        now = datetime.datetime(2018, 1, 1)
        input = {"key": [{"key2": [{"relative-datestamp": "1 day"}]}]}
        self.assertEqual(
            resolve_timestamps(now, input),
            {"key": [{"key2": ["2018-01-02T00:00:00Z"]}]},
        )

    def test_appears_with_other_keys(self):
        now = datetime.datetime(2018, 1, 1)
        input = [{"relative-datestamp": "1 day", "another-key": True}]
        self.assertEqual(
            resolve_timestamps(now, input),
            [{"relative-datestamp": "1 day", "another-key": True}],
        )


class TestTaskRefs(unittest.TestCase):
    def do(self, input, output):
        self.assertEqual(
            resolve_docker_image_references(
                "subject",
                input,
                docker_images={
                    "image_reference1": "image1",
                    "image_reference2": "image2",
                    "image_reference3": "image3",
                },
            ),
            output,
        )

    def test_no_change(self):
        "resolve_docker_image_references does nothing when there are no task references"
        self.do(
            {"in-a-list": ["stuff", {"property": "<image_reference1>"}]},
            {"in-a-list": ["stuff", {"property": "<image_reference1>"}]},
        )

    def test_in_list(self):
        "resolve_docker_image_references resolves task references in a list"
        self.do(
            {"in-a-list": ["stuff", {"docker_image_reference": "<image_reference1>"}]},
            {"in-a-list": ["stuff", "image1"]},
        )

    def test_in_dict(self):
        "resolve_docker_image_references resolves task references in a dict"
        self.do(
            {"in-a-dict": {"stuff": {"docker_image_reference": "<image_reference2>"}}},
            {"in-a-dict": {"stuff": "image2"}},
        )

    def test_multiple(self):
        "resolve_docker_image_references resolves multiple references in the same string"
        self.do(
            {
                "multiple": {
                    "docker_image_reference": "stuff <image_reference1> stuff "
                    "<image_reference2> after",
                }
            },
            {"multiple": "stuff image1 stuff image2 after"},
        )

    def test_embedded(self):
        "resolve_docker_image_references resolves ebmedded references"
        self.do(
            {
                "embedded": {
                    "docker_image_reference": "stuff before <image_reference3> stuff after"
                }
            },
            {"embedded": "stuff before image3 stuff after"},
        )

    def test_multikey(self):
        "resolve_docker_image_references is ignored when there is another key in the dict"
        self.do(
            {
                "escape": {
                    "docker_image_reference": "<image_reference3>",
                    "another-key": True,
                }
            },
            {
                "escape": {
                    "docker_image_reference": "<image_reference3>",
                    "another-key": True,
                }
            },
        )

    def test_invalid(self):
        "resolve_docker_image_references raises a KeyError on reference to an invalid task"
        self.assertRaisesRegex(
            KeyError,
            'job "subject" has no docker image named "no-such"',
            lambda: resolve_docker_image_references(
                "subject",
                {"docker_image_reference": "<no-such>"},
                docker_images={},
            ),
        )
