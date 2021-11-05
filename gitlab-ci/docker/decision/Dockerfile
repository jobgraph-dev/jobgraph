ARG DOCKER_IMAGE_PARENT
FROM $DOCKER_IMAGE_PARENT

COPY --chown="$RUNNER_USER:$RUNNER_USER" src /jobgraph/src
COPY --chown="$RUNNER_USER:$RUNNER_USER" setup.py python-version.txt /jobgraph/
COPY --chown="$RUNNER_USER:$RUNNER_USER" requirements/base.in requirements/base.txt /jobgraph/requirements/
RUN pip install --user --require-hashes --requirement '/jobgraph/requirements/base.txt' && \
    pip install --user --no-deps --editable "/jobgraph"
