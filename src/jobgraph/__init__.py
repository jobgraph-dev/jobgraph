# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


# Maximum number of dependencies a single job can have.
MAX_DEPENDENCIES = 50

# Enable fast task generation for local debugging
# This is normally switched on via the --fast/-F flag to `mach taskgraph`
# Currently this skips toolchain task optimizations and schema validation
fast = False
