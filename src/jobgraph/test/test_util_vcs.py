# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import os
import subprocess

import pytest

from jobgraph.util.vcs import get_repository

_FORCE_COMMIT_DATE_TIME = "2019-11-04T10:03:58+00:00"


_GIT_DATE_ENV_VARS = ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE")


@pytest.fixture(scope="function")
def git_repo(tmpdir):
    env = _build_env_with_git_date_env_vars(_FORCE_COMMIT_DATE_TIME)

    repo_dir = _init_repo(tmpdir, "git")

    subprocess.check_output(
        ["git", "config", "user.email", "integration@tests.test"], cwd=repo_dir, env=env
    )
    subprocess.check_output(
        ["git", "config", "user.name", "Integration Tests"], cwd=repo_dir, env=env
    )
    subprocess.check_output(
        ["git", "commit", "-m", "First commit"], cwd=repo_dir, env=env
    )

    yield repo_dir


def _build_env_with_git_date_env_vars(date_time_string):
    env = os.environ.copy()
    env.update({env_var: date_time_string for env_var in _GIT_DATE_ENV_VARS})
    return env


def _init_repo(tmpdir, repo_type):
    repo_dir = tmpdir.strpath
    first_file_path = tmpdir.join("first_file")
    first_file_path.write("first piece of data")

    subprocess.check_output([repo_type, "init"], cwd=repo_dir)
    subprocess.check_output([repo_type, "add", first_file_path.strpath], cwd=repo_dir)

    return repo_dir


@pytest.fixture
def repo(git_repo):
    return get_repository(git_repo)


@pytest.mark.parametrize(
    "commit_message",
    (
        "commit message in… pure utf8",
        "commit message in... ascii",
    ),
)
def test_get_commit_message(repo, commit_message):
    some_file_path = os.path.join(repo.path, "some_file")
    with open(some_file_path, "w") as f:
        f.write("some data")

    repo.run("add", some_file_path)
    repo.run("commit", "-m", commit_message)

    assert repo.get_commit_message() == commit_message


def test_calculate_head_ref(repo):
    assert repo.head_ref == "c34844580592fcf4575b8f1174285b853b566d85"


def test_get_repo_path(repo):
    repo.run("remote", "add", "origin", "https://some/repo")
    repo.run("remote", "add", "other", "https://some.other/repo")

    assert repo.get_url() == "https://some/repo"
    assert repo.get_url("other") == "https://some.other/repo"


def test_update(repo):
    bar = os.path.join(repo.path, "bar")
    with open(bar, "w") as fh:
        fh.write("bar")

    first_ref = repo.head_ref
    repo.run("add", bar)
    repo.run("commit", "-m", "Second commit")

    second_ref = repo.head_ref
    repo.update(first_ref)
    assert repo.head_ref == first_ref

    repo.update(second_ref)
    assert repo.head_ref == second_ref


def test_branch(repo):
    if repo.tool == "git":
        assert repo.branch == "main"
        repo.run("checkout", "-b", "test")
    else:
        assert repo.branch is None
        repo.run("bookmark", "test")

    assert repo.branch == "test"

    bar = os.path.join(repo.path, "bar")
    with open(bar, "w") as fh:
        fh.write("bar")

    repo.run("add", bar)
    repo.run("commit", "-m", "Second commit")
    assert repo.branch == "test"

    repo.update(repo.head_ref)
    assert repo.branch is None

    repo.update("test")
    assert repo.branch == "test"


def test_working_directory_clean(repo):
    assert repo.working_directory_clean()

    # untracked file
    bar = os.path.join(repo.path, "bar")
    with open(bar, "w") as fh:
        fh.write("bar")

    assert repo.working_directory_clean()
    assert not repo.working_directory_clean(untracked=True)
    repo.run("add", "bar")
    assert not repo.working_directory_clean()

    repo.run("commit", "-m", "Second commit")
    assert repo.working_directory_clean()

    # modified file
    with open(bar, "a") as fh:
        fh.write("bar2")
    assert not repo.working_directory_clean()

    if repo.tool == "git":
        repo.run("reset", "--hard", "HEAD")
    else:
        repo.run("revert", "-a")
    assert repo.working_directory_clean()

    # removed file
    repo.run("rm", bar)
    assert not repo.working_directory_clean()
