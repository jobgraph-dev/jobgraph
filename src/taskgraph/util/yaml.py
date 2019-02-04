# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import, print_function, unicode_literals

import os
import yaml


def load_yaml(*parts):
    """Convenience function to load a YAML file in the given path.  This is
    useful for loading kind configuration files from the kind path."""
    filename = os.path.join(*parts)
    with open(filename, "rb") as f:
        return yaml.safe_load(f)