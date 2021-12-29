"""
.. include:: ../../README.md
"""


# Maximum number of dependencies a single job can have.
MAX_UPSTREAM_DEPENDENCIES = 50

# Enable fast task generation for local debugging
# This is normally switched on via the --fast/-F flag.
# Currently this skips toolchain task optimizations and schema validation
fast = False
