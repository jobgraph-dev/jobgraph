# The following implementation is a pure copy of [1]. distutils will be removed
# in python 3.12 and there is no plan to move strtobool() elsewhere.
#
# [1] https://github.com/python/cpython/blob/v3.10.0/Lib/distutils/util.py#L308
# [2] https://www.python.org/dev/peps/pep-0632/#migration-advice
def strtobool(val):
    """Convert a string representation of truth to true (1) or false (0).
    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.
    """
    val = val.lower()
    if val in ("y", "yes", "t", "true", "on", "1"):
        return 1
    elif val in ("n", "no", "f", "false", "off", "0"):
        return 0
    else:
        raise ValueError(f"invalid truth value {val!r}")
