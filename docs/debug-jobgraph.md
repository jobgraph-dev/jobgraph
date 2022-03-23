# Debug jobgraph

Like any piece of software, jobgraph itself or your own setup of jobgraph likely contain bugs. Jobgraph aims to make debugging easier than on vanilla Gitlab CI.

## Artifacts output by the decision job

The decision job generates logs which are usually useful when it turns red. When this is green but doesn't generate the pipeline you expect, you can have a look at the other artifacts stored on the job:

 * `generated-gitlab-ci.yml` (and any `generated-include-X.yml`) are the files intepreted by Gitlab CI. The job configurations in there are fully described and don't contain any logic or indirections. If a job is missing, then it got removed in an earlier step.
 * `optimized-job-graph.yml` is the same as the above files but all combined into a single one. As a matter of fact, Gitlab has a [hard limit on the files](https://docs.gitlab.com/ee/administration/instance_limits.html#maximum-size-and-depth-of-cicd-configuration-yaml-files) it interprets.
 * `target-jobs.yml` shows the jobs that were targetted but not optimized away. Here is [the difference](docs/the-journey-of-a-job-configuration.md) between a targetted job and an optimized one is.
 * `full-job-graph.yml` shows the full graph including non-targetted and optimized ones.
 * `parameters.yml` displays all parameters that the decision job dealt with. You can download this file to mimic the exact same behavior locally.

## Run jobgraph locally

First and foremost, you need to [install the source code](../README.md#install-the-source-code) of jobgraph on your machine. Then:

 1. `cd` to the root of your repository
 1. download the `parameters.yml` file from a decision job (see above)
 1. `jobgraph optimized --parameters parameters.yml --output-file optimized-job-graph.yml`

This should output the same optimized job graph as the decision job you would like to debug.

## Hook a debugger

Jobgraph uses python. As such, it's easy to add a `breakpoint()` to get the Python Debugger (pdb) running. In any of the python files (transforms, optimizations, target filters, etc.) and no matter if it's your code or jobgraph's, you can just add `breakpoint()` and rerun jobgraph on your machine. Then, you can follow the execution flow or have a look at the content of some job configurations.

See [this article](https://www.askpython.com/python/built-in-methods/python-breakpoint-function) for more information about `breakpoint()`.


## In a nutshell

Jobgraph gives multiple ways to understand why a decision job didn't act the way you expect it to. You can start from the job that ran on Gitlab CI all the way to your own machine with your own tweaks. Feel free to [create an issue](-/issues/new) if you would like to make the debugging experience more enjoyable!
