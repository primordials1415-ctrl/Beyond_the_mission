from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ASSET_DIR = BASE_DIR / "assets"

SCREEN_W, SCREEN_H = 960, 540
FPS = 60
MAP_W, MAP_H = 2400, 1600
BORDER = 48  # impassable rocky edge of the map

PLAYER_SPEED = 170   # px / second
GHOST_SPEED = 120

CYAN = (80, 235, 255)
PANEL = (10, 16, 26)
TEXT = (225, 240, 245)
DIM = (120, 150, 160)
