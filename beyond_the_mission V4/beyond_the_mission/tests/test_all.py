"""All seven encounters, pygame stubbed (logic only, not a real run)."""
import sys
from types import SimpleNamespace as NS
from unittest.mock import MagicMock
sys.modules["pygame"] = MagicMock()
sys.path.insert(0, "..")
import pygame, story_data
from game import Game
from interaction import InteractionSystem
from journal import StoryProgress
from discovery import EncounterManager, INSERT_TIME
import sprites
E = NS(type=pygame.KEYDOWN, key=pygame.K_e)

for eq in story_data.EQUIPMENT:       # every entry has what an encounter needs
    for k in ("site", "tint", "intro_lines", "thanks_lines", "recovery_lines", "capsule_title", "cutscene_text"):
        assert eq.get(k), (eq["id"], k)
    assert eq["id"] in sprites.WRECK_ART and eq["id"] in sprites.GHOST_ROBOT_ART
    sprites.WRECK_ART[eq["id"]](); sprites.GHOST_ROBOT_ART[eq["id"]](0)   # callable with stub

g = Game.__new__(Game)
g.progress = StoryProgress(); g.scene = None; g.toast = None; g.state = "play"
g.interaction = InteractionSystem(); g.encounters = EncounterManager(g.progress, g.start_encounter)
g.progress.signal_detected = True
order = [e["id"] for e in story_data.EQUIPMENT]
for n, eid in enumerate(order):
    assert eid in g.encounters.robots
    assert not any(o in g.encounters.robots and not g.progress.is_recovered(o) and o != eid for o in order)
    assert not g.progress.is_available(order[n + 1] if n + 1 < 7 else eid) or n == 6
    robot = g.encounters.robots[eid]
    g.interaction.target = robot; g.interaction.handle_event(E)
    for _ in range(len(robot.lines)): g.interaction.handle_event(E)
    s = g.scene; assert g.state == "scene" and s.phase == "choice", eid
    for expect in ("minigame", "capsule", "insert"):
        s.handle_event(E); assert s.phase == expect
    s.update(INSERT_TIME + 0.1); s.handle_event(E); assert s.phase == "cutscene"
    s.handle_event(E)
    assert g.state == "play" and g.progress.recovered == order[:n + 1], eid
    for _ in range(len(g.interaction.active.lines)): g.interaction.handle_event(E)
    assert not g.interaction.in_dialogue
    print(eid, "encounter: PASS")
assert g.progress.current() is None and story_data.objective(g.progress) == "All lost memories recovered!"
assert g.progress.archive.integrity == 1.0
print("full 7-step sequence: PASS")
