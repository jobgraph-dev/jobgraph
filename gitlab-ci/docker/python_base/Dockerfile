FROM python:3.10-alpine@sha256:affe0faa14e7553fc570beec3864e74b5e36f8c19b2bb49ae8ba79c0e9e7236e

ENV RUNNER_USER='runner' \
    RUNNER_HOME='/runner'

RUN mkdir -p "$RUNNER_HOME" && \
    adduser --disabled-password --home "$RUNNER_HOME" "$RUNNER_USER"

# Gitlab CI usually clone the git repository under /builds.
# That's why we're setting the default workdir there.
RUN mkdir -p "/builds/" && \
    chown -R "$RUNNER_USER:$RUNNER_USER" "/builds/"
WORKDIR "/builds/"

RUN apk update && \
    apk add --no-cache --update git~=2.34

USER "$RUNNER_USER"
ENV PATH="$RUNNER_HOME/.local/bin:$PATH" \
    USER="$RUNNER_USER"

RUN mkdir -p "$RUNNER_HOME/.local/bin"

# Set default command to shell so that decision jobs can run other shell commands like `pip`.
CMD ["/bin/ash", "--login"]
