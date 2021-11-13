#!/usr/bin/env sh

# TODO: Make this script a Python one. The complexity is now too high.

set -e

GIT_REMOTE="${1:-origin}"
GIT_BRANCH="${2:-update-jobgraph-dependencies}"

jobgraph update-dependencies

git switch --force-create "$GIT_BRANCH"
git config user.name '[Bot] Jobgraph Cron'
git config user.email ''
git commit --all --message 'Run jobgraph update-dependencies' || (echo 'No updates found' && exit 0)

GIT_REMOTE_URL="$(git remote get-url "$GIT_REMOTE")"
URL_WITHOUT_HTTPS_NOR_BASIC_AUTH="$(echo "$GIT_REMOTE_URL" | sed 's/^https:\/\/\([^@]*@\)\?/git@/')"
URL_WITH_COLON="${URL_WITHOUT_HTTPS_NOR_BASIC_AUTH/\//:}"
SSH_URL="${URL_WITH_COLON%/}"

git remote set-url --push "$GIT_REMOTE" "$SSH_URL"
GIT_MAIN_BRANCH="$(git ls-remote --symref "$GIT_REMOTE" HEAD | awk '/^ref:/ {sub(/refs\/heads\//, "", $2); print $2}')"

git push "$GIT_REMOTE" "$GIT_BRANCH" \
    --force \
    --push-option='merge_request.create' \
    --push-option='merge_request.label="cron"' \
    --push-option='merge_request.merge_when_pipeline_succeeds' \
    --push-option='merge_request.remove_source_branch' \
    --push-option="merge_request.target=$GIT_MAIN_BRANCH" \
    --push-option='merge_request.title="Update jobgraph dependencies"'
