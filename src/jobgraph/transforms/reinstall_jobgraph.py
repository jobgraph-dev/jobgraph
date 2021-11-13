from jobgraph.transforms.base import TransformSequence

transforms = TransformSequence()


@transforms.add
def add_before_script(config, jobs):
    for job in jobs:
        if job.pop("reinstall-jobgraph", False):
            before_script = job.setdefault("before_script", [])
            before_script.append(
                "pip install --prefix '/runner/.local' --no-deps --editable ."
            )

        yield job
