import os
import fastf1
from fastf1 import plotting

def configurar_cache(cache_dir):
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    fastf1.Cache.enable_cache(cache_dir)
    plotting.setup_mpl(misc_mpl_mods=False)