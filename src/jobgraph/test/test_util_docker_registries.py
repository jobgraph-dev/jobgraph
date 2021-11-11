# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from jobgraph.util import docker_registries

_IMAGE_DATA_PER_FULL_LOCATION = {
    "some-group/some-image:some-tag": {
        "digest": "",
        "image_name": "some-image",
        "namespace": "some-group",
        "registry": "index.docker.io",
        "tag": "some-tag",
    },
    "python:3.10": {
        "digest": "",
        "image_name": "python",
        "namespace": "library",
        "registry": "index.docker.io",
        "tag": "3.10",
    },
    "python:3.10-alpine@sha256:ab08dd9e48afe4cf629d993a41dccf0a74ae08f556b25cb143d8de37b25e1525": {  # noqa E501
        "digest": "sha256:ab08dd9e48afe4cf629d993a41dccf0a74ae08f556b25cb143d8de37b25e1525",  # noqa E501
        "image_name": "python",
        "namespace": "library",
        "registry": "index.docker.io",
        "tag": "3.10-alpine",
    },
    "registry.gitlab.com/johanlorenzo/jobgraph/decision@sha256:92dbab416ab1538e2df8daf6880f2383bb1719d7e73d1954c0d19d4054d687b9": {  # noqa E501
        "digest": "sha256:92dbab416ab1538e2df8daf6880f2383bb1719d7e73d1954c0d19d4054d687b9",  # noqa E501
        "image_name": "decision",
        "namespace": "johanlorenzo/jobgraph",
        "registry": "registry.gitlab.com",
        "tag": "latest",
    },
    "registry.Gitlab.com/JohanLorenzo/jobgraph/Decision:20a3d0f40f466fcbe8f741bd4ce8f7a6843dc2fd4a97858a1b3c83eeb283b015": {  # noqa E501
        "digest": "",
        "image_name": "decision",
        "namespace": "johanlorenzo/jobgraph",
        "registry": "registry.gitlab.com",
        "tag": "20a3d0f40f466fcbe8f741bd4ce8f7a6843dc2fd4a97858a1b3c83eeb283b015",
    },
}


@pytest.mark.parametrize(
    "image_full_location, expected", _IMAGE_DATA_PER_FULL_LOCATION.items()
)
def test_parse_image_full_location(image_full_location, expected):
    assert docker_registries._parse_image_full_location(image_full_location) == expected


@pytest.mark.parametrize("expected, image_data", _IMAGE_DATA_PER_FULL_LOCATION.items())
def test_build_image_full_location(image_data, expected):
    assert docker_registries.build_image_full_location(image_data) == expected.lower()
