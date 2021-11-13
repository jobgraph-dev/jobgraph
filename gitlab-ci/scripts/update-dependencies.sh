#!/usr/bin/env sh

set -e

GIT_REMOTE="${1:-origin}"
GIT_BRANCH="${2:-update-jobgraph-dependencies}"

jobgraph update-dependencies

git switch --force-create "$GIT_BRANCH"
git config author.name '[Bot] Jobgraph Cron'
git config author.email ''
git commit --all --message 'Run jobgraph update-dependencies' || (echo 'No updates found' && exit 0)

GIT_MAIN_BRANCH="$(git ls-remote --symref "$GIT_REMOTE" HEAD | awk '/^ref:/ {sub(/refs\/heads\//, "", $2); print $2}')"

git push "$GIT_REMOTE" "$GIT_BRANCH" \
    --force \
    --push-option='merge_request.create' \
    --push-option='merge_request.label="cron"' \
    --push-option='merge_request.merge_when_pipeline_succeeds' \
    --push-option='merge_request.remove_source_branch' \
    --push-option="merge_request.target=$GIT_MAIN_BRANCH" \
    --push-option='merge_request.title="Update jobgraph dependencies"'
