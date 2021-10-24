#!/usr/bin/env ash

# This runs in docker to pin our requirements files.
set -e

pip install --upgrade pip
pip install pip-compile-multi

pip-compile-multi --generate-hashes base --generate-hashes test --generate-hashes dev
chmod 644 requirements/*.txt
