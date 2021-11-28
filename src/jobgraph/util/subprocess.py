import subprocess


def run_subprocess(*args, **kwargs):
    subprocess.run(*args, **kwargs, check=True)
