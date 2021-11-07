FROM python:3.10-alpine@sha256:ab08dd9e48afe4cf629d993a41dccf0a74ae08f556b25cb143d8de37b25e1525

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

# Set default command to shell so that decision jobs can run other shell commands like `pip`.
CMD ["/bin/ash", "--login"]
