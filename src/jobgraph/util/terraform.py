from jobgraph.util.subprocess import run_subprocess


def terraform_init(
    terraform_dir,
    gitlab_project_id,
    gitlab_root_url,
    terraform_username,
    terraform_password,
    upgrade_providers=False,
):
    terraform_command = [
        "terraform",
        "init",
    ]

    if upgrade_providers:
        terraform_command.append("-upgrade")

    if not (terraform_dir / ".terraform").is_dir():
        backend_url = (
            f"{gitlab_root_url}/api/v4/projects/"
            f"{gitlab_project_id}/terraform/state/jobgraph"
        )

        terraform_command.extend(
            [
                f"-backend-config=address={backend_url}",
                f"-backend-config=lock_address={backend_url}/lock",
                f"-backend-config=unlock_address={backend_url}/lock",
                f"-backend-config=username={terraform_username}",
                f"-backend-config=password={terraform_password}",
                "-backend-config=lock_method=POST",
                "-backend-config=unlock_method=DELETE",
                "-backend-config=retry_wait_min=5",
            ]
        )

    run_subprocess(terraform_command, cwd=terraform_dir)


def terraform_apply(terraform_dir, **kwargs):
    terraform_command = ["terraform", "apply", "-auto-approve"]
    for variable_key, variable_value in kwargs.items():
        terraform_command.extend(["-var", f"{variable_key}={variable_value}"])

    run_subprocess(terraform_command, cwd=terraform_dir)
