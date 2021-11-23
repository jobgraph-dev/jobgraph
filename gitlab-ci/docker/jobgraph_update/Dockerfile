ARG DOCKER_IMAGE_PARENT
FROM $DOCKER_IMAGE_PARENT

USER root
RUN apk add --no-cache \
    bash~=5.1 \
    build-base~=0.5 \
    curl~=7.79 \
    docker~=20.10 \
    gzip~=1.10 \
    openssh~=8.6 \
    tar~=1.34

USER "$RUNNER_USER"

COPY --chown="$RUNNER_USER:$RUNNER_USER" requirements/test.txt requirements/dev.txt /jobgraph/requirements/
RUN pip install --user --no-cache-dir --require-hashes --requirement '/jobgraph/requirements/dev.txt'

ENV SSH_DIR="$RUNNER_HOME/.ssh"
RUN mkdir -p "$SSH_DIR" && chmod 700 "$SSH_DIR"
COPY --chown="$RUNNER_USER:$RUNNER_USER" gitlab-ci/docker/jobgraph_update/known_hosts "$SSH_DIR/known_hosts"

ENV TFENV_SHA_FILE="$RUNNER_HOME/tfenv.sha256" \
    TFENV_TARGET_DIR="$RUNNER_HOME/tfenv"

ENV PATH="$TFENV_TARGET_DIR/bin:$PATH"

COPY --chown="$RUNNER_USER:$RUNNER_USER" gitlab-ci/docker/jobgraph_update/tfenv.sha256 "$TFENV_SHA_FILE"
RUN TFENV_VERSION="$(sed -E 's/[0-9a-f]+  tfenv-(.+)\.tar\.gz/\1/' "$TFENV_SHA_FILE")" && \
    TFENV_ARCHIVE="$RUNNER_HOME/tfenv-$TFENV_VERSION.tar.gz" && \
    curl --location "https://github.com/tfutils/tfenv/archive/refs/tags/v$TFENV_VERSION.tar.gz" --output "$TFENV_ARCHIVE" && \
    sha256sum -c "$TFENV_SHA_FILE" && \
    mkdir -p "$TFENV_TARGET_DIR" && \
    tar xvf "$TFENV_ARCHIVE" --strip-components=1 --directory="$TFENV_TARGET_DIR" && \
    rm "$TFENV_ARCHIVE"

COPY --chown="$RUNNER_USER:$RUNNER_USER" gitlab-ci/terraform/.terraform-version "$RUNNER_HOME"
RUN tfenv install
