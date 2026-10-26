"""Shared credential validation and bounded rotation windows."""
import hmac
import os
import time
import math


def matches(supplied, expected):
    return bool(supplied and expected) and hmac.compare_digest(
        supplied.encode('utf-8'), expected.encode('utf-8'))


def current_or_previous(supplied, name):
    if matches(supplied, os.environ.get(name, '')):
        return True
    try:
        deadline = float(os.environ.get(name + '_PREVIOUS_UNTIL', '0'))
    except ValueError:
        return False
    return math.isfinite(deadline) and time.time() < deadline and matches(supplied, os.environ.get(name + '_PREVIOUS', ''))
