# The "decision job" pattern

## Vanilla Gitlab CI

![How a pipeline gets spawned in vanilla Gitlab CI](docs/images/vanilla-gitlab-ci.svg)

Out of the box, Gitlab CI generates pipelines based on the content of `.gitlab-ci.yml` and on the state of the git repository. For example: whenever a git-push happens, Gitlab evaluates the content of `.gitlab-ci.yml` and spawns the jobs that are meant to run on such an event. This model is usually sufficient in most cases. However, it may be too limited in some others. For instance: you may want to publish an artifact only if it wasn't already published by another pipeline. Another example: you may want to configure your Gitlab CI jobs with more than just some YAML.

## The decision job pattern

![How a pipeline gets spawned with a decision job](docs/images/decision-job.svg)

In order to address the limitations of vanilla Gitlab CI, we have to run some code we own. This code is executed in its own job: the decision job. Since we have a way to control this job, we can make it interract with any external data source: other pipelines, other types of repositories, etc. The decision job has its own code, so you're not just bound to solely YAML to describe what you want your pipelines to do. In specific case of Gitlab CI, this pattern leverages [parent-child pipelines](https://docs.gitlab.com/ee/ci/pipelines/parent_child_pipelines.html).

Jobgraph is an implementation of the "decision job" pattern.
