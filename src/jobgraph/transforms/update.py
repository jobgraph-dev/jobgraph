from jobgraph.transforms.base import TransformSequence
from jobgraph.util.schema import resolve_keyed_by

transforms = TransformSequence()


@transforms.add
def resolve_keyed_variables(config, jobs):
    for job in jobs:
        for key in ("optimization",):
            resolve_keyed_by(
                job,
                key,
                item_name=job["name"],
                **{
                    "pipeline_source": config.params["pipeline_source"],
                },
            )

        yield job
