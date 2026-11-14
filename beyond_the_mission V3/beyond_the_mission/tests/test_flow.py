"""State-flow test with pygame STUBBED (MagicMock): exercises the real InteractionSystem,
EncounterManager, EncounterScene and Game story methods. Not a real run of the game."""
import sys
from types import SimpleNamespace as NS
from unittest.mock import MagicMock
sys.modules["pygame"] = MagicMock()
sys.path.insert(0, "..")
import pygame
import story_data
from game import Game
from interaction import InteractionSystem
from journal import StoryProgress
from discovery import EncounterManager, INSERT_TIME

def key(k): return NS(type=pygame.KEYDOWN, key=k)
E = key(pygame.K_e)

g = Game.__new__(Game)
g.progress = StoryProgress(); g.scene = None; g.toast = None; g.state = "play"
g.interaction = InteractionSystem()
g.encounters = EncounterManager(g.progress, g.start_encounter)

# only Ingenuity's robot exists at start (no skipping ahead)
assert list(g.encounters.robots) == ["ingenuity"]
robot = g.encounters.robots["ingenuity"]

# intro dialogue (3 lines) -> signal detected
g.start_story()
assert g.interaction.in_dialogue
for _ in range(3): g.interaction.handle_event(E)
assert not g.interaction.in_dialogue and g.progress.signal_detected
print("intro dialogue -> signal: PASS")

# interact with Ghost Ingenuity: 6 lines then challenge choice opens
g.interaction.target = robot
g.interaction.handle_event(E)
assert g.interaction.active is robot and g.state == "play"
for _ in range(len(robot.lines)): g.interaction.handle_event(E)
assert g.state == "scene" and g.scene.phase == "choice"
print("robot dialogue -> choice panel: PASS")

s = g.scene
s.handle_event(E);  assert s.phase == "minigame"
assert s.challenge.title == "Minigame Placeholder"
s.handle_event(E);  assert s.phase == "capsule"            # Continue -> capsule reward
assert not g.progress.is_recovered("ingenuity")
s.handle_event(E);  assert s.phase == "insert"             # Insert into Archive
assert g.progress.recovered == ["ingenuity"]
s.handle_event(E);  assert s.phase == "insert"             # button locked during animation
s.update(INSERT_TIME + 0.1)
s.handle_event(E);  assert s.phase == "cutscene"
s.handle_event(E)                                          # Skip
assert g.scene is None and g.state == "play"
assert g.toast and g.toast[0] == "Memory Successfully Recovered!"
assert g.interaction.in_dialogue and g.interaction.active.lines == story_data.BY_ID["ingenuity"]["recovery_lines"]
for _ in range(2): g.interaction.handle_event(E)
assert not g.interaction.in_dialogue
assert g.progress.current()["id"] == "insight"
assert "More lost memories" in story_data.objective(g.progress)
print("minigame -> capsule -> archive -> cutscene -> recovery: PASS")

# no repeat: robot now says thanks and never reopens the scene
g.encounters.refresh()
assert robot.lines == story_data.BY_ID["ingenuity"]["thanks_lines"]
g.start_encounter(story_data.BY_ID["ingenuity"]); assert g.scene is None and g.state == "play"
g.interaction.target = robot; g.interaction.handle_event(E)
for _ in range(len(robot.lines)): g.interaction.handle_event(E)
assert g.scene is None and g.progress.recovered == ["ingenuity"]
print("no duplicate encounter / capsule: PASS")

# "Not Yet" cancels without reward
g2 = Game.__new__(Game)
g2.progress = StoryProgress(); g2.scene = None; g2.toast = None; g2.state = "play"
g2.interaction = InteractionSystem(); g2.encounters = EncounterManager(g2.progress, g2.start_encounter)
g2.start_encounter(story_data.BY_ID["ingenuity"]); assert g2.state == "scene"
g2.scene.handle_event(key(pygame.K_d)); g2.scene.handle_event(E)
assert g2.state == "play" and g2.scene is None and g2.progress.recovered == []
print("'Not Yet' cancel: PASS")
