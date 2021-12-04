ARG DOCKER_IMAGE_PARENT
FROM $DOCKER_IMAGE_PARENT as common

ENV TFENV_TARGET_DIR="$RUNNER_HOME/tfenv"
ENV PATH="$TFENV_TARGET_DIR/bin:$PATH"


FROM common as builder

USER root

# The first group are build dependencies (removed later on).
# The second one are runtime dependencies
RUN apk add --no-cache \
    build-base~=0.5 \
    curl~=7.79 \
    gzip~=1.10 \
    tar~=1.34 \
    \
    bash~=5.1 \
    docker~=20.10 \
    jq~=1.6 \
    openssh~=8.6

USER "$RUNNER_USER"

ENV TFENV_SHA_FILE="$RUNNER_HOME/tfenv.sha256" \
    TERRAFORM_VERSION_FILE="$RUNNER_HOME/.terraform-version"

COPY --chown="$RUNNER_USER:$RUNNER_USER" gitlab-ci/docker/decision/tfenv.sha256 "$TFENV_SHA_FILE"
RUN TFENV_VERSION="$(sed -E 's/[0-9a-f]+  tfenv-(.+)\.tar\.gz/\1/' "$TFENV_SHA_FILE")" && \
    TFENV_ARCHIVE="$RUNNER_HOME/tfenv-$TFENV_VERSION.tar.gz" && \
    curl --location "https://github.com/tfutils/tfenv/archive/refs/tags/v$TFENV_VERSION.tar.gz" --output "$TFENV_ARCHIVE" && \
    sha256sum -c "$TFENV_SHA_FILE" && \
    mkdir -p "$TFENV_TARGET_DIR" && \
    tar xvf "$TFENV_ARCHIVE" --strip-components=1 --directory="$TFENV_TARGET_DIR" && \
    rm "$TFENV_ARCHIVE"

COPY --chown="$RUNNER_USER:$RUNNER_USER" terraform/.terraform-version "$TERRAFORM_VERSION_FILE"
RUN tfenv install && tfenv use


ENV GITLAB_TERRAFORM_PATH="$RUNNER_HOME/.local/bin/gitlab-terraform"
RUN curl --location 'https://gitlab.com/gitlab-org/terraform-images/-/raw/37f671b7abb6d29ee033fd7586b29caf7b270182/src/bin/gitlab-terraform.sh' --output "$GITLAB_TERRAFORM_PATH" && \
    chmod +x "$GITLAB_TERRAFORM_PATH"

USER root

# Remove build dependencies
RUN rm "$TFENV_SHA_FILE" "$TERRAFORM_VERSION_FILE" && \
    apk del build-base \
    curl \
    gzip \
    tar

USER "$RUNNER_USER"


FROM common

COPY --from=builder / /

ENV JOBGRAPH_DIR='/jobgraph'

COPY --chown="$RUNNER_USER:$RUNNER_USER" src "$JOBGRAPH_DIR/src"
COPY --chown="$RUNNER_USER:$RUNNER_USER" setup.py python-version.txt "$JOBGRAPH_DIR"/
COPY --chown="$RUNNER_USER:$RUNNER_USER" requirements/base.in requirements/base.txt "$JOBGRAPH_DIR"/requirements/
RUN pip install --user --no-cache-dir --require-hashes --requirement "$JOBGRAPH_DIR"/requirements/base.txt && \
    pip install --user --no-cache-dir --no-deps --editable "$JOBGRAPH_DIR"


ENV SSH_DIR="$RUNNER_HOME/.ssh"
RUN mkdir -p "$SSH_DIR" && chmod 700 "$SSH_DIR"
COPY --chown="$RUNNER_USER:$RUNNER_USER" gitlab-ci/docker/decision/known_hosts "$SSH_DIR/known_hosts"

COPY --chown="$RUNNER_USER:$RUNNER_USER" terraform/*.tf "$JOBGRAPH_DIR"/terraform/
