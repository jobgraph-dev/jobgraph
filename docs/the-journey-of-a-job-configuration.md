# The journey of a job configuration

## Part 1: what you will regularly use

Using Jobgraph is usually about dealing with this part of the data flow.

![First part of the flow](docs/images/the-journey-of-a-job-configuration-part1.svg)


### `stage.yml`

Jobgraph pushes Gitlab's concept of [stage](https://docs.gitlab.com/ee/ci/yaml/index.html#stage) a little bit further. Stages now group jobs that are very similar.
For instance: You’d like to have 2 compilation jobs, one for a debug build and the other for a production-ready one. Chances are both builds are generated with the same command, modulo a flag. In Jobgraph, you will define both jobs under the same stage.

Each stage is stored in its own `stage.yml` file. It’s the configuration-oriented part of Jobgraph. You usually put raw data in them. There are some bits of simple logic that you can put in them.
For example: `job-defaults` provides some default values for all jobs defined in the stage, it can be useful if the build jobs are generated with the same command.

In addition to the actual configuration of a job, a stage defines 2 new concepts: a loader and a series of transforms.

### Loader

The loader is in charge of taking every job in the stage, applying `job-defaults` and finding what the right upstream dependencies are. The dependency links are what make the graphs of jobs.
For instance: In addition to having common values, both of your build jobs may depend on Docker images, where your full build environment is stored. The loader will output the 2 build jobs and set the docker image as their dependencies.

ℹ️ You sometimes want jobs based on other files in your git repository, like a manifest used by your build system (e.g.: some `pom.xml` files if you're using maven). You can make your own loader that will look into these files, extract the suitable data and pass it to the next step.

### Transforms

Here comes the programming oriented part of Jobgraph. The configuration defined in `stage.yml` is usually defined to be as simple as possible. Transforms take them and translate them into actual job configuration.

For example: Say your repository contains several modules all built separately. Each module has its own name, is located in a subdirectory dependending on the name, and has some build options also dependending on the name. So, `stage.yml` will just contain the app name and you can write your own transforms to provide the missing data (i.e.: subdirectories and build options) based on that app name. In vanilla Gitlab CI, you have to: either write down every piece of configuration for each module, or interpolate the missing data when the job starts. Maintainability is impacted in both cases: on one hand, you have to manually maintain all bits of configurations, on the other hand, you don't have any results unti the job is actually run. Jobgraph allows you to solve both problems!

Moreover, transforms can be shared among stages, which gives a way to factorize common logic.


ℹ️ Some transforms even validate their input, ensuring the dataflow is sane, as if you ran the Gitlab CI linter!

## Part 2: what may become handy from times to times.

You may not need it, but that’s how optimization happens!

![Second part of the flow](docs/images/the-journey-of-a-job-configuration-part2.svg)

### Target jobs

Jobgraph always generates the full graph, then it filters out what’s not needed. That’s what the target job phase does.

For instance: You want to run a scheduled pipeline with a handful of jobs. The target jobs phase will only select the right jobs.


### Optimized jobs

Example 1: Some jobs are not needed to run because no file has changed in the current git-push. These jobs are excluded in this phase. That's the equivalent of the `rules` keyword in vanilla Gitlab CI.

Example 2: Some jobs may have already complete in a previous pipeline. If so, Jobgraph takes them out even if they were part of the target jobs.


### Submit the pipeline to Gitlab CI

At this point, Jobgraph knows exactly what subgraph to submit. It generates a yml file containing each job definition and submit them as [a child pipeline](https://docs.gitlab.com/ee/ci/pipelines/parent_child_pipelines.html). The rest behaves as it usually does on Gitlab CI!


## Need any help?

If you’re stuck on something or Jobgraph isn’t behaving as it should, feel free to [open a new issue](https://gitlab.com/jobgraph-dev/jobgraph/-/issues/new).
