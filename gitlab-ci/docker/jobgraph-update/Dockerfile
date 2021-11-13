ARG DOCKER_IMAGE_PARENT
FROM $DOCKER_IMAGE_PARENT

USER root
RUN apk add --no-cache \
    docker~=20.10 \
    openssh~=8.6

USER "$RUNNER_USER"

ENV SSH_DIR="$RUNNER_HOME/.ssh"

RUN mkdir -p "$SSH_DIR" && chmod 700 "$SSH_DIR"
COPY --chown="$RUNNER_USER:$RUNNER_USER" gitlab-ci/docker/jobgraph-update/known_hosts "$SSH_DIR/known_hosts"
