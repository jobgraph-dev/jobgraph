# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import os
import subprocess
from abc import ABC, abstractproperty, abstractmethod
from shutil import which


class Repository(ABC):
    def __init__(self, path):
        self.path = path
        self.binary = which(self.tool)
        if self.binary is None:
            raise OSError(f"{self.tool} not found!")

    def run(self, *args: str):
        cmd = (self.binary,) + args
        return subprocess.check_output(cmd, cwd=self.path, universal_newlines=True)

    @abstractproperty
    def tool(self) -> str:
        """Version control system being used which is usually 'git'."""

    @abstractproperty
    def head_ref(self) -> str:
        """Hash of HEAD revision."""

    @abstractproperty
    def base_ref(self):
        """Hash of revision the current topic branch is based on."""

    @abstractproperty
    def branch(self):
        """Current branch or bookmark the checkout has active."""

    @abstractmethod
    def get_url(self, remote=None):
        """Get URL of the upstream repository."""

    @abstractmethod
    def get_commit_message(self, revision=None):
        """Commit message of specified revision or current commit."""

    @abstractmethod
    def working_directory_clean(self, untracked=False, ignored=False):
        """Determine if the working directory is free of modifications.

        Returns True if the working directory does not have any file
        modifications. False otherwise.

        By default, untracked and ignored files are not considered. If
        ``untracked`` or ``ignored`` are set, they influence the clean check
        to factor these file classes into consideration.
        """

    @abstractmethod
    def update(self, ref):
        """Update the working directory to the specified reference."""


class GitRepository(Repository):
    tool = "git"

    @property
    def head_ref(self):
        return self.run("rev-parse", "--verify", "HEAD").strip()

    @property
    def base_ref(self):
        refs = self.run(
            "rev-list", "HEAD", "--topo-order", "--boundary", "--not", "--remotes"
        ).splitlines()
        if refs:
            return refs[-1][1:]  # boundary starts with a prefix `-`
        return self.head_ref

    @property
    def branch(self):
        return self.run("branch", "--show-current").strip() or None

    def get_url(self, remote="origin"):
        return self.run("remote", "get-url", remote).strip()

    def get_commit_message(self, revision=None):
        revision = revision or self.head_ref
        return self.run("log", "-n1", "--format=%B")

    def working_directory_clean(self, untracked=False, ignored=False):
        args = ["status", "--porcelain"]

        # Even in --porcelain mode, behavior is affected by the
        # ``status.showUntrackedFiles`` option, which means we need to be
        # explicit about how to treat untracked files.
        if untracked:
            args.append("--untracked-files=all")
        else:
            args.append("--untracked-files=no")

        if ignored:
            args.append("--ignored")

    def update(self, ref):
        self.run("checkout", ref)

    def get_list_of_changed_files(self, base_revision, head_revision):
        return self.run("diff", "--no-color", "--name-only", f"{base_revision}..{head_revision}").splitlines()


def get_repository(path):
    """Get a repository object for the repository at `path`.
    If `path` is not a known VCS repository, raise an exception.
    """
    if os.path.exists(os.path.join(path, ".git")):
        return GitRepository(path)

    raise RuntimeError("Current directory is not a git repository")
