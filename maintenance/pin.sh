#!/usr/bin/env bash
set -ex

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
ROOT_DIR="$(cd -- "$(dirname -- "$SCRIPT_DIR")" &> /dev/null && pwd)"

PYTHON_VERSION="$(cat $ROOT_DIR/python-version.txt)"

docker run \
    --tty \
    --volume "$ROOT_DIR:/src" \
    --workdir '/src' \
    --pull 'always' \
    "python:$PYTHON_VERSION-alpine" \
    'maintenance/pin-helper.sh'

CURRENT_USER="$(id -un)"
CURRENT_GROUP="$(id -gn)"

sudo chown -R "$CURRENT_USER:$CURRENT_GROUP" "$ROOT_DIR/requirements"
