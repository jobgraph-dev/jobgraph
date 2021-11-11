ARG DOCKER_IMAGE_PARENT
FROM $DOCKER_IMAGE_PARENT

USER root
RUN apk add --no-cache build-base~=0.5

USER "$RUNNER_USER"
COPY --chown="$RUNNER_USER:$RUNNER_USER" requirements/base.txt requirements/test.txt /jobgraph/requirements/
RUN pip install --user --no-cache-dir --require-hashes --requirement '/jobgraph/requirements/test.txt'
