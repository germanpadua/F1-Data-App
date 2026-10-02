import os
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


