import os
import time
from datetime import datetime

import fastf1
from fastf1 import plotting
import numpy as np

def configurar_cache(cache_dir):
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    fastf1.Cache.enable_cache(cache_dir)


def get_selectable_seasons(first_season=2018):
    """Return the seasons offered in the year selector: first_season..current year."""
    current_year = datetime.now().year
    return list(range(first_season, current_year + 1))

def rotate(xy, *, angle):
    rot_mat = np.array([[np.cos(angle), np.sin(angle)],
                        [-np.sin(angle), np.cos(angle)]])
    return np.matmul(xy, rot_mat)


# Sentinel returned by fetch_with_retry when every attempt raised.
RETRY_FAILED = object()


def fetch_with_retry(func, *args, max_attempts=3, initial_delay=2.0, **kwargs):
    """Call func and retry on any exception with exponential backoff.

    Returns the result on success. After exhausting max_attempts, returns the
    RETRY_FAILED sentinel instead of raising, so callers can skip the failed
    item and continue (e.g. one round of Ergast standings).
    """
    delay = initial_delay
    for attempt in range(max_attempts):
        try:
            return func(*args, **kwargs)
        except Exception:
            if attempt == max_attempts - 1:
                return RETRY_FAILED
            time.sleep(delay)
            delay *= 2


