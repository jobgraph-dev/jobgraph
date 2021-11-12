from jobgraph.transforms.base import TransformSequence

transforms = TransformSequence()


@transforms.add
def add_variables(config, jobs):
    for job in jobs:
        variables = job.setdefault("variables", {})
        # See
        # https://docs.gitlab.com/ee/ci/docker/using_docker_build.html#docker-in-docker-with-tls-enabled-in-kubernetes
        variables |= {
            "DOCKER_HOST": "tcp://docker:2376",
            "DOCKER_TLS_CERTDIR": "/certs",
            "DOCKER_TLS_VERIFY": "1",
            "DOCKER_CERT_PATH": "$DOCKER_TLS_CERTDIR/client",
        }

        services = job.setdefault("services", [])
        services.append({"docker-image-reference": "<docker-in-docker>"})

        yield job
