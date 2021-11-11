FROM python:3.10-alpine@sha256:b2264d27b94d35e76f4a9cf54c803733e626aabb3dc54a5a62e8491b7202d044

ENV RUNNER_USER='runner' \
    RUNNER_HOME='/runner'

RUN mkdir -p "$RUNNER_HOME" && \
    adduser --disabled-password --home "$RUNNER_HOME" "$RUNNER_USER"

RUN apk update && \
    apk add --no-cache --update git~=2.32

USER "$RUNNER_USER"
WORKDIR "$RUNNER_HOME"
ENV PATH="$RUNNER_HOME/.local/bin:$PATH" \
    USER="$RUNNER_USER"

# Set default command to shell so that decision jobs can run other shell commands like `pip`.
CMD ["/bin/ash", "--login"]
