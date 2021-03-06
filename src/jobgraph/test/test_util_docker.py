import os
import shutil
import stat
import sys
import tarfile
import tempfile
import unittest

import pytest

from jobgraph.util import docker

MODE_STANDARD = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH


class TestDocker(unittest.TestCase):
    @pytest.mark.xfail(sys.version_info >= (3, 8), reason="Hash is different")
    def test_generate_context_hash(self):
        tmpdir = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmpdir, "docker", "my-image"))
            p = os.path.join(tmpdir, "docker", "my-image", "Dockerfile")
            with open(p, "w") as f:
                f.write("FROM node\nADD a-file\n")
            os.chmod(p, MODE_STANDARD)
            p = os.path.join(tmpdir, "docker", "my-image", "a-file")
            with open(p, "w") as f:
                f.write("data\n")
            os.chmod(p, MODE_STANDARD)
            self.assertEqual(
                docker.generate_context_hash(
                    tmpdir, os.path.join(tmpdir, "docker/my-image"), "my-image"
                ),
                "e1649b3427bd7a0387f4508d25057c2e89228748517aad6c70e3df54f47bd13a",
            )
        finally:
            shutil.rmtree(tmpdir)

    @pytest.mark.xfail(sys.version_info >= (3, 8), reason="Hash is different")
    def test_create_context_tar_basic(self):
        tmp = tempfile.mkdtemp()
        try:
            d = os.path.join(tmp, "test_image")
            os.mkdir(d)
            with open(os.path.join(d, "Dockerfile"), "a"):
                pass
            os.chmod(os.path.join(d, "Dockerfile"), MODE_STANDARD)

            with open(os.path.join(d, "extra"), "a"):
                pass
            os.chmod(os.path.join(d, "extra"), MODE_STANDARD)

            tp = os.path.join(tmp, "tar")
            h = docker.create_context_tar(tmp, d, tp, "my_image")
            self.assertEqual(
                h, "6c1cc23357625f64f775a08eace7bbc3877dd08d2f3546e0f2e308bac8491865"
            )

            # File prefix should be "my_image"
            with tarfile.open(tp, "r:gz") as tf:
                self.assertEqual(
                    tf.getnames(),
                    [
                        "Dockerfile",
                        "extra",
                    ],
                )
        finally:
            shutil.rmtree(tmp)

    @pytest.mark.xfail(sys.version_info >= (3, 8), reason="Hash is different")
    def test_create_context_topsrcdir_files(self):
        tmp = tempfile.mkdtemp()
        try:
            d = os.path.join(tmp, "test-image")
            os.mkdir(d)
            with open(os.path.join(d, "Dockerfile"), "wb") as fh:
                fh.write(b"# %include extra/file0\n")
            os.chmod(os.path.join(d, "Dockerfile"), MODE_STANDARD)

            extra = os.path.join(tmp, "extra")
            os.mkdir(extra)
            with open(os.path.join(extra, "file0"), "a"):
                pass
            os.chmod(os.path.join(extra, "file0"), MODE_STANDARD)

            tp = os.path.join(tmp, "tar")
            h = docker.create_context_tar(tmp, d, tp, "test_image")
            self.assertEqual(
                h, "e7f14044b8ec1ba42e251d4b293af212ad08b30ec8ab6613abbdbe73c3c2b61f"
            )

            with tarfile.open(tp, "r:gz") as tf:
                self.assertEqual(
                    tf.getnames(),
                    [
                        "Dockerfile",
                        "topsrcdir/extra/file0",
                    ],
                )
        finally:
            shutil.rmtree(tmp)

    @pytest.mark.xfail(sys.version_info >= (3, 8), reason="Hash is different")
    def test_create_context_extra_directory(self):
        tmp = tempfile.mkdtemp()
        try:
            d = os.path.join(tmp, "test-image")
            os.mkdir(d)

            with open(os.path.join(d, "Dockerfile"), "wb") as fh:
                fh.write(b"# %include extra\n")
                fh.write(b"# %include file0\n")
            os.chmod(os.path.join(d, "Dockerfile"), MODE_STANDARD)

            extra = os.path.join(tmp, "extra")
            os.mkdir(extra)
            for i in range(3):
                p = os.path.join(extra, f"file{i}")
                with open(p, "wb") as fh:
                    content = f"file{i}"
                    fh.write(content)
                os.chmod(p, MODE_STANDARD)

            with open(os.path.join(tmp, "file0"), "a"):
                pass
            os.chmod(os.path.join(tmp, "file0"), MODE_STANDARD)

            tp = os.path.join(tmp, "tar")
            h = docker.create_context_tar(tmp, d, tp, "my_image")

            self.assertEqual(
                h, "d2a3363b15d0eb547a6c81a72ddf3980e2f6e6360c29b4fb6818102896f43180"
            )

            with tarfile.open(tp, "r:gz") as tf:
                self.assertEqual(
                    tf.getnames(),
                    [
                        "Dockerfile",
                        "topsrcdir/extra/file0",
                        "topsrcdir/extra/file1",
                        "topsrcdir/extra/file2",
                        "topsrcdir/file0",
                    ],
                )
        finally:
            shutil.rmtree(tmp)
