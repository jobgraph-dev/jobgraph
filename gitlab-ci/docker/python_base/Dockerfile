FROM python:3.10-alpine@sha256:60469fac3d4c1c4781465b18f1a89d8dd2a01af9bb799d17836b972fcc463da9

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
