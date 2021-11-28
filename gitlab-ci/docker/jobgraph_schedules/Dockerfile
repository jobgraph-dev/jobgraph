ARG DOCKER_IMAGE_PARENT
FROM $DOCKER_IMAGE_PARENT

RUN mkdir -p '/jobgraph/terraform'
COPY --chown="$RUNNER_USER:$RUNNER_USER" terraform/*.tf /jobgraph/terraform/
