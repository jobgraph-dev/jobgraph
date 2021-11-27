from pathlib import Path

from jobgraph.paths import get_gitlab_ci_yml_path
from jobgraph.util.vcs import get_repository


def bootstrap():
    cwd = Path.cwd()
    get_repository(cwd)
    generate_gitlab_ci_yml(cwd)


def generate_gitlab_ci_yml(cwd):
    source_gitlab_ci_yml = get_gitlab_ci_yml_path()

    with open(source_gitlab_ci_yml) as f:
        gitlab_ci_yml_lines = f.readlines()

    target_lines = [
        line
        for line in gitlab_ci_yml_lines
        if all(
            excluded_line not in line
            for excluded_line in (
                # These lines are specific to the jobgraph repo itself
                "# We reinstall jobgraph",
                "- pip install --prefix ",
            )
        )
    ]

    with open(get_gitlab_ci_yml_path(root_dir=cwd), "w") as f:
        f.writelines(target_lines)
