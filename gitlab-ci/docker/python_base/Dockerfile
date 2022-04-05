FROM python:3.10-alpine@sha256:63689f3a9b5641ad0c1092ceead25c9ec7ad9aaa13d274ab4a2e05683f28001b

ENV DEFAULT_WORKDIR='/builds' \
    RUNNER_USER='runner' \
    RUNNER_HOME='/runner'

RUN mkdir -p "$RUNNER_HOME" && \
    adduser --disabled-password --home "$RUNNER_HOME" "$RUNNER_USER"

# Gitlab CI usually clone the git repository under /builds.
# That's why we're setting the default workdir there.
RUN mkdir -p "$DEFAULT_WORKDIR" && \
    chown -R "$RUNNER_USER:$RUNNER_USER" "$DEFAULT_WORKDIR"
WORKDIR "$DEFAULT_WORKDIR"

RUN apk update && \
    apk add --no-cache --update git~=2.34

USER "$RUNNER_USER"
ENV PATH="$RUNNER_HOME/.local/bin:$PATH" \
    USER="$RUNNER_USER"

RUN mkdir -p "$RUNNER_HOME/.local/bin"

# Set default command to shell so that decision jobs can run other shell commands like `pip`.
CMD ["/bin/ash", "--login"]
