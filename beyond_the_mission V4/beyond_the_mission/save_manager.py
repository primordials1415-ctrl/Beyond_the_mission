"""Save/load for Beyond the Mission (no pygame; JSON on disk).

Progression lives in journal.StoryProgress (archive capsules + signal flag).
This module only serialises that object, so new equipment added to
story_data.EQUIPMENT is picked up automatically.

Public API:
    has_save_file()                  -> bool
    save_game(progress, player_pos)  -> bool   (atomic write, keeps a .bak)
    load_game()                      -> (progress, player_pos) or None
    new_game()                       -> fresh StoryProgress (deletes old save)
    last_error                       -> short reason string after a failed load
"""
import json
import os
import tempfile
from pathlib import Path

from settings import BASE_DIR, MAP_W, MAP_H
from story_data import EQUIPMENT
from journal import StoryProgress

SAVE_VERSION = 1
SAVE_PATH = Path(BASE_DIR) / "savegame.json"      # next to the game files, any launch dir
BACKUP_PATH = SAVE_PATH.with_suffix(".json.bak")
ORDER = [e["id"] for e in EQUIPMENT]

# Equipment ids from older builds -> current ids (Spirit + Opportunity became one).
LEGACY_IDS = {"spirit": "twin_trails", "opportunity": "twin_trails"}

last_error = ""


# ------------------------------------------------------------------ helpers
def _clean_capsules(raw):
    """Known ids only, no duplicates, and a strict prefix of the story order
    (challenges unlock one after another, so a gap can never be valid)."""
    if not isinstance(raw, list):
        return []
    have = set()
    for c in raw:
        c = LEGACY_IDS.get(c, c)
        if c in ORDER:
            have.add(c)
    out = []
    for eid in ORDER:
        if eid not in have:
            break
        out.append(eid)
    return out


def _clean_pos(raw):
    try:
        x, y = float(raw[0]), float(raw[1])
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    if not (0 < x < MAP_W and 0 < y < MAP_H):
        return None
    return (x, y)


def _migrate(data):
    """Bring an older save dict up to SAVE_VERSION. Add steps here later."""
    v = data.get("version", 0)
    if not isinstance(v, int) or v > SAVE_VERSION:
        raise ValueError("incompatible save version")
    # v0 -> v1: nothing structural changed; ids are cleaned in _clean_capsules.
    data["version"] = SAVE_VERSION
    return data


def _parse(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("save is not an object")
    data = _migrate(data)
    prog = data.get("progress")
    if not isinstance(prog, dict):
        raise ValueError("missing progress")
    p = StoryProgress.from_dict({"capsules": _clean_capsules(prog.get("capsules")),
                                 "signal": bool(prog.get("signal", False))})
    return p, _clean_pos(data.get("player"))


# --------------------------------------------------------------- public API
def has_save_file():
    return SAVE_PATH.exists() or BACKUP_PATH.exists()


def save_game(progress, player_pos=None):
    """Atomic write: temp file -> fsync -> replace. Previous save kept as .bak."""
    global last_error
    data = {"version": SAVE_VERSION, "progress": progress.to_dict()}
    if player_pos is not None:
        data["player"] = [round(float(player_pos[0]), 1), round(float(player_pos[1]), 1)]
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=str(SAVE_PATH.parent), prefix=".save_", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if SAVE_PATH.exists():
            try:
                os.replace(SAVE_PATH, BACKUP_PATH)
            except OSError:
                pass
        os.replace(tmp, SAVE_PATH)
        return True
    except OSError as e:
        last_error = f"Could not write save: {e}"
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        return False


def load_game():
    """Return (StoryProgress, player_pos or None), or None if nothing usable.
    Falls back to the backup if the main file is corrupt."""
    global last_error
    last_error = ""
    for path in (SAVE_PATH, BACKUP_PATH):
        if not path.exists():
            continue
        try:
            return _parse(path)
        except (OSError, ValueError, TypeError, KeyError) as e:   # JSONDecodeError is a ValueError
            last_error = f"Save file unreadable ({e.__class__.__name__})."
    if not last_error:
        last_error = "No save file found."
    return None


def new_game():
    """Start over: remove any existing save and return fresh progress."""
    for path in (SAVE_PATH, BACKUP_PATH):
        try:
            path.unlink()
        except OSError:
            pass
    return StoryProgress()
