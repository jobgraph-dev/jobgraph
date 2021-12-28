# Jobgraph

Make your Gitlab CI Pipelines scale up! Jobgraph lets you abstract complexity away while making sure your pipelines stand the test of time.

## What does Jobgraph do?

Jobgraph enables your Gitlab CI pipelines to:
 1. **scale up**  
 *Jobgraph lets you define jobs dynamically based on the state of the repository and other external factors.*
 1. **be reproducible**  
 *Jobgraph pins as many moving parts as possible.*
 1. **get automatic (yet reproducible) updates**  
 *Jobgraph ensure these pinned parts get regularly bumped.*
 1. **be debuggable more easily**  
 *Jobgraph outputs exactly what jobs are going to be run and lets you hook a debugger if needed.*
 1. **avoid footguns**  
 *Jobgraph uses exiting linters to highlight bad usages of Docker, Python, or yaml.*

## Is Jobgraph suited for your project?

You would be interested in Jobgraph if:
 * **your pipelines don't always look the way you expected them to**  
 *Jobgraph allows you to reproduce/debug one of its runs locally.*
 * **your project fits in a sizable monorepo**  
 *Jobgraph is able to generate complex Gitlab CI's pipelines that can't easily fit in a single `.gitlab-ci.yml` file.*
 * **you had to generate a `.gitlab-ci.yml`**  
 *Jobgraph takes this responsibility by leveraging Gitlab's [child pipeline](https://docs.gitlab.com/ee/ci/pipelines/parent_child_pipelines.html) feature.*
 * **your CI uses your custom docker images**  
 *Jobgraph makes these docker images part of the pipeline and rebuild them only when needed.*
 * **you don't want to manually manage job dependencies**  
 *Jobgraph programmatically fulfills the `needs` of your Gitlab CI jobs.*

## Origin

Jobgraph is a fork of [Mozilla's Taskgraph](https://hg.mozilla.org/ci/taskgraph/), which makes Firefox ships on a daily basis. Taskgraph supports another Continuous Integration (CI) system: Taskcluster. Both of them cope with CI pipelines containing 10,000 jobs for a single release. Jobgraph aims to bring Gitlab CI to this level of complexity 🙂

## Jobgraph at high-level


See this [blogpost](https://johanlorenzo.github.io/blog/2019/10/24/taskgraph-is-now-deployed-to-the-biggest-mozilla-mobile-projects.html) which summarizes Taskgraph's basic usage and functionalities. The blog post predates Jobgraph but the concepts are the same.

*// TODO: Convert this blog post to the jobgraph lingo.*

### Usage

The repository first needs to be cloned and then install the ``jobgraph``
within the virtual environment.

```sh
$ git clone https://gitlab.com/jobgraph-dev/jobgraph/
$ cd <location-where-jobgraph-has-been-cloned>
$ mkvirtualenv jobgraph
# ensure we get the development version of it locally to be able to work with it
$ (jobgraph) pip install -e .
# now one can change directory to the github project that needs jobgraph, e.g. Fenix
$ (jobgraph) cd <location-where-fenix-has-been-cloned>
$ (jobgraph) jobgraph --help
```

TODO: Write the rest of the documentation
