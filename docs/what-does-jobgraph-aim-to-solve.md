# What does Jobgraph aim to solve?


## Gitlab CI pipelines and jobs, in a few words

[A job](https://docs.gitlab.com/ee/ci/jobs/) is an arbitrary piece of code that gets executed by Gitlab CI. We tell Gitlab CI to execute a job by submitting some configuration. This job configuration contains data about what commands to run, for instance. You will quickly need more than a single job to perform all actions. In this case, Gitlab CI lets you submit [CI/CD pipelines](https://docs.gitlab.com/ee/ci/pipelines/). These pipelines are usually defined in a single `.gitlab-ci.yml` file when there are only a handful of jobs.


## When `.gitlab-ci.yml` gets convoluted

At some point, configuring pipelines with tens of jobs in a `.gitlab-ci.yml` gets error-prone. Over the years, Gitlab has offered some ways to reduce the complexity. For example, you can:

 * provide default values with YAML anchors and the [`extends` keyword](https://docs.gitlab.com/ee/ci/yaml/index.html#extends).
 * inject job configurations from other files (including remote ones) thanks to the [`include` keyword](https://docs.gitlab.com/ee/ci/yaml/index.html#include).
 * [lint](https://docs.gitlab.com/ee/ci/lint.html) your `.gitlab-ci.yml` file and view the merged YAML.

Although, some pain points are still hard to debug:

 * [`rules` statements](https://docs.gitlab.com/ee/ci/yaml/index.html#rules) are only evaluated at runtime and there is little debugging options when something doesn't behave as expected.
 * job ordering (via [`needs`](https://docs.gitlab.com/ee/ci/yaml/index.html#needs) and [`stages`](https://docs.gitlab.com/ee/ci/yaml/index.html#stages)) has to be manually implemented and maintained.
 * when some heavy changes are made to the pipeline configuration, it can be hard to test every possible scenario efficiently.

Jobgraph aims to fix these pain points while enhancing what Gitlab has offered.


## About the name "Jobgraph"

As your project grows, you have to define and optimize dependencies between jobs. Thus you define a graph of jobs. Hence the name, "Jobgraph".


## The "decision job" pattern

Like said above, you can submit a pipeline by defining all jobs in a [.gitlab-ci.yml file](https://docs.gitlab.com/ee/ci/yaml/index.html) in your repository.

Jobgraph implements a different pattern: the "decision job". You basically configure a single job in `.gitlab-ci.yml`. This job decides what jobs are going to be scheduled based on any factor you want. You are not limited by the [`rules` keywords](https://docs.gitlab.com/ee/ci/yaml/index.html#rules) and the variables it's able to evaluate. This means you could let jobgraph talk to a given API to decides whether this job can be skipped or not. It's actually what jobgraph does natively with docker images 😉

Once Jobgraph decided what to schedule, it outputs each job configuration to a file which kicks off a [child pipeline](https://docs.gitlab.com/ee/ci/pipelines/parent_child_pipelines.html). Two pretty nice side effects: the generated file is downloadable (it's an artifact of the decision job) and it's WYSIWYG (only the expected jobs are in there).


## Try this at home!

The decision job exposes another artifact: `parameters.yml`. Download it and feed it to your local Jobgraph and you're able to debug why your pipeline is not the one you expected. Store several `parameters.yml` and you're able to test your pipelines against several scenarios (e.g.: a regular git push, a merge request, a git tag, etc.). No need to perform these actions manually anymore!


## Breaking down complexity

The "decision job" pattern alone doesn't solve all the reasons a `.gitlab-ci.yml` may get too complex. Jobgraph splits job configurations into several smaller parts. Want to know more? See [The journey of a job configuration](docs/the-journey-of-a-job-configuration.md)


## Need any help?

If you’re stuck on something or Jobgraph isn’t behaving as it should, feel free to [open a new issue](https://gitlab.com/jobgraph-dev/jobgraph/-/issues/new).
