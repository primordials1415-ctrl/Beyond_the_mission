"""Asset loader. To replace a placeholder, drop a PNG at the path given to
load_image (relative to assets/), e.g. assets/player/walk_down_0.png."""
import pygame
from settings import ASSET_DIR

_cache = {}


def load_image(rel_path, fallback):
    if rel_path not in _cache:
        path = ASSET_DIR / rel_path
        if path.exists():
            _cache[rel_path] = pygame.image.load(str(path)).convert_alpha()
        else:
            _cache[rel_path] = fallback()
    return _cache[rel_path]
