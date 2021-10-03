Jobgraph
=========

Jobgraph generates complex Gitlab CI's pipelines that can't easily fit in a single ``.gitlab-ci.yml`` file. It is well suited for monorepos.

Jobgraph is a fork of `Mozilla's Taskgraph`_. The latter supports another Continuous Integration (CI) system: Taskcluster. Taskgraph scales up pretty well. It manages to generate pipelines that contains more than 10,000 jobs for Firefox. Jobgraph hopes to bring Gitlab CI to this level of complexity.

Jobgraph/Taskgraph at high-level
--------------------------------

See this `blogpost`_ which summarizes Taskgraph's basic usage and functionalities. It was written before Jobgraph was a thing but the concepts are the same.

In practice for singular graphs
-------------------------------

Jobgraph is nice as it allows to break the graph generations at
different levels. Whether that’s just before submission to Gitlab CI
or earlier.

Usage
~~~~~

The repository first needs to be cloned and then install the ``jobgraph``
within the virtual environment.

::

   $ hg clone https://hg.mozilla.org/ci/jobgraph/
   $ cd <location-where-jobgraph-has-been-cloned>
   $ mkvirtualenv jobgraph
   # ensure we get the development version of it locally to be able to work with it
   $ (jobgraph) pip install -e .
   # now one can change directory to the github project that needs jobgraph, e.g. Fenix
   $ (jobgraph) cd <location-where-fenix-has-been-cloned>
   $ (jobgraph) jobgraph --help

TODO: Write the rest of the documentation

.. _Mozilla's Taskgraph: https://hg.mozilla.org/ci/taskgraph/
.. _blogpost: https://johanlorenzo.github.io/blog/2019/10/24/taskgraph-is-now-deployed-to-the-biggest-mozilla-mobile-projects.html
