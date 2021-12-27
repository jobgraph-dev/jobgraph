import os
import re
import subprocess
from abc import ABC, abstractmethod, abstractproperty
from copy import copy
from pathlib import Path
from shutil import which

from jobgraph.paths import JOBGRAPH_ROOT_DIR_IN_DOCKER


class Repository(ABC):
    def __init__(self, path):
        self.path = path
        self.binary = which(self.tool)
        if self.binary is None:
            raise OSError(f"{self.tool} not found!")

    def run(self, *args: str, env=None):
        cmd = (self.binary,) + args

        new_env = copy(os.environ)
        if env:
            new_env |= env

        return subprocess.check_output(
            cmd, cwd=self.path, env=new_env, universal_newlines=True
        )

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


NULL_GIT_COMMIT = "0000000000000000000000000000000000000000"
DEFAULT_REMOTE_NAME = "origin"
_LS_REMOTE_PATTERN = re.compile(r"ref:\s+refs/heads/(?P<branch_name>\S+)\s+HEAD")


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

    def switch_branch(self, branch, force_create=False):
        command = ["switch"]
        if force_create:
            command.append("--force-create")
        command.append(branch)
        self.run(*command)

    @property
    def tracked_files(self):
        return {Path(file) for file in self.run("ls-files").splitlines()}

    def get_default_branch(self, remote=DEFAULT_REMOTE_NAME, short_format=False):
        try:
            # This call works if you have (network) access to the repo
            return self._get_default_branch_from_remote_query(remote, short_format)
        except subprocess.CalledProcessError:
            pass

        try:
            # this one works if the current repo was cloned from an existing
            # repo elsewhere
            return self._get_default_branch_from_cloned_metadata(remote, short_format)
        except subprocess.CalledProcessError:
            pass

        # this one is the last resort in case the remote is not accessible and
        # the local repo is where `git init` was made
        return self._guess_default_branch(remote, short_format)

    def _get_default_branch_from_remote_query(self, remote, short_format):
        # This function requires network access to the repo
        output = self.run("ls-remote", "--symref", remote, "HEAD")
        matches = _LS_REMOTE_PATTERN.search(output)
        if not matches:
            raise RuntimeError(
                f'Could not find the default branch of remote repository "{remote}". '
                "Got: {output}"
            )

        short_branch_name = matches.group("branch_name")
        if short_format:
            return short_branch_name
        return f"{remote}/{short_branch_name}"

    def _get_default_branch_from_cloned_metadata(self, remote, short_format):
        output = self.run("rev-parse", "--abbrev-ref", f"{remote}/HEAD").strip()
        if short_format:
            return "/".join(output.split("/")[1:])
        return output

    def _guess_default_branch(self, remote, short_format):
        branches = [
            line.strip()
            for line in self.run("branch", "--all", "--no-color").splitlines()
        ]
        for candidate_branch in ("main", "master"):
            if f"remotes/{remote}/{candidate_branch}" in branches:
                if short_format:
                    return candidate_branch
                return f"{remote}/{candidate_branch}"

        raise RuntimeError(f"Unable to find default branch. Got: {branches}")

    def get_url(self, remote=DEFAULT_REMOTE_NAME):
        return self.run("remote", "get-url", remote).strip()

    def set_push_url(self, url, remote=DEFAULT_REMOTE_NAME):
        return self.run("remote", "set-url", "--push", remote, url)

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
        return self.run(
            "diff", "--no-color", "--name-only", f"{base_revision}..{head_revision}"
        ).splitlines()

    def find_first_common_revision(self, base_branch, head_rev):
        return self.run("merge-base", base_branch, head_rev).strip()

    def get_file_at_given_revision(self, revision, file_path):
        return self.run("show", f"{revision}:{file_path}").strip()

    def commit(self, committer_name, committer_email, message, commit_all_files=False):
        command = ["commit", "--message", message]
        if commit_all_files:
            command.append("--all")

        self.run(
            *command,
            env={
                "GIT_AUTHOR_EMAIL": committer_email,
                "GIT_AUTHOR_NAME": committer_name,
                "GIT_COMMITTER_EMAIL": committer_email,
                "GIT_COMMITTER_NAME": committer_name,
            },
        )

    def push(self, remote_name, branch, force_push=False, push_options=None):
        push_options = [] if push_options is None else push_options

        command = ["push", "--verbose", remote_name, branch]
        if force_push:
            command.append("--force")

        command.extend([f"--push-option={push_option}" for push_option in push_options])

        self.run(*command)

    def does_commit_exist_locally(self, commit_sha):
        try:
            return self.run("cat-file", "-t", commit_sha).strip() == "commit"
        except subprocess.CalledProcessError as e:
            # Error code 128 comes with the message:
            # "git cat-file: could not get object info"
            if e.returncode == 128:
                return False
            raise


class JobgraphInDockerImageFakeGitRepository(Repository):
    tool = "git"

    @property
    def head_ref(self):
        return NULL_GIT_COMMIT

    @property
    def base_ref(self):
        return NULL_GIT_COMMIT

    @property
    def branch(self):
        return NULL_GIT_COMMIT

    def switch_branch(self, branch, force_create=False):
        pass

    @property
    def tracked_files(self):
        return sorted(list(Path(self.path).glob("**/*")))

    def get_default_branch(self, *args, **kwargs):
        return NULL_GIT_COMMIT

    def get_url(self, *args, **kwargs):
        return "https://gitlab.com/JohanLorenzo/jobgraph"

    def set_push_url(self, *args, **kwargs):
        pass

    def get_commit_message(self, revision=None):
        return "No commit message"

    def working_directory_clean(self, *args, **kwargs):
        pass

    def update(self, ref):
        pass

    def get_list_of_changed_files(self, *args, **kwargs):
        return []

    def find_first_common_revision(self, *args, **kwargs):
        return NULL_GIT_COMMIT

    def get_file_at_given_revision(self, revision, file_path):
        with open(file_path) as f:
            return f.read().strip()

    def commit(self, *args, **kwargs):
        pass

    def push(self, *args, **kwargs):
        pass

    def does_commit_exist_locally(self, *args, **kwargs):
        return False


def get_repository(path):
    """Get a repository object for the repository at `path`.
    If `path` is not a known VCS repository, raise an exception.
    """
    path_ = Path(path)
    if (path_ / ".git").exists():
        return GitRepository(path)
    elif path_ == JOBGRAPH_ROOT_DIR_IN_DOCKER:
        return JobgraphInDockerImageFakeGitRepository(path)

    raise RuntimeError(f'"{path}" is not the root of a git repository')
