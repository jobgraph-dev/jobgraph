# TODO: Factorize this docker image with the python one
FROM python:3.10-alpine@sha256:78604a29496b7a1bd5ea5c985d69a0928db7ea32fcfbf71bbde3e317fdd9ac5e

ENV RUNNER_USER='runner' \
    RUNNER_HOME='/runner'

RUN mkdir -p "$RUNNER_HOME" && \
    adduser --disabled-password --home "$RUNNER_HOME" "$RUNNER_USER"

RUN apk update && \
    apk add --no-cache --update git

USER "$RUNNER_USER"
WORKDIR "$RUNNER_HOME"
ENV PATH="$RUNNER_HOME/.local/bin:$PATH" \
    USER="$RUNNER_USER"

COPY --chown="$RUNNER_USER:$RUNNER_USER" src /jobgraph/src
COPY --chown="$RUNNER_USER:$RUNNER_USER" setup.py python-version.txt /jobgraph/
COPY --chown="$RUNNER_USER:$RUNNER_USER" requirements/base.in requirements/base.txt /jobgraph/requirements/
RUN pip install --user --require-hashes --requirement '/jobgraph/requirements/base.txt' && \
    pip install --user --no-deps --editable "/jobgraph"

# Set default command to shell so that decision jobs can run other shell commands like `pip`.
CMD ["/bin/ash", "--login"]
