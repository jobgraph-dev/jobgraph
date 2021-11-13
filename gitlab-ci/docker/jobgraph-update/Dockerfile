ARG DOCKER_IMAGE_PARENT
FROM $DOCKER_IMAGE_PARENT

USER root
RUN apk add --no-cache \
    docker~=20.10 \
    openssh~=8.6

USER "$RUNNER_USER"
