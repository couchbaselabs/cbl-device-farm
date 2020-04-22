#!/usr/bin/env python3

import sys


MIN_PY_VERSION = (3, 5, 0)


def ensure_min_python_version():
    if sys.version_info < MIN_PY_VERSION:
        found_ver = ".".join(str(i) for i in sys.version_info[:3])
        required_ver = ".".join(str(i) for i in MIN_PY_VERSION)
        raise AssertionError("Python {} required (detected {})".format(required_ver, found_ver))
