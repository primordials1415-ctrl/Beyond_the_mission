"""Challenges. To add a real minigame: write a class with the same interface as
PlaceholderChallenge (handle_event -> "done" when finished, update, draw) and
register it in CHALLENGES under the equipment id."""
import ui

PLACEHOLDER_TEXT = ("This challenge is currently under development. "
                    "You can continue to recover this equipment's memories.")


class PlaceholderChallenge:
    title = "Minigame Placeholder"

    def __init__(self, eq):
        self.eq = eq
        self.buttons = ui.ButtonRow(["Continue"], 335)

    def handle_event(self, e):
        return "done" if self.buttons.handle_event(e) == 0 else None

    def update(self, dt):
        pass

    def draw(self, surf):
        rect = ui.center_panel(surf, 640, 280)
        ui.draw_title(surf, self.title, rect.y + 28)
        ui.draw_wrapped(surf, PLACEHOLDER_TEXT, 32, rect.inflate(-60, 0), rect.y + 100)
        self.buttons.draw(surf)



from ingenuity_game import IngenuityChallenge
from insight_game import MartianWhisper
from phoenix_game import PhoenixChallenge
from viking_game import VikingChallenge
from sojourner_game import SojournerChallenge
from twin_trails import TwinTrailsChallenge

# Equipment ID -> Challenge class
CHALLENGES = {
    "ingenuity": IngenuityChallenge,
    "insight": MartianWhisper,
    "phoenix": PhoenixChallenge,
    "viking": VikingChallenge,
    "sojourner": SojournerChallenge,
    "twin_trails": TwinTrailsChallenge,
}


def make_challenge(eq):
    return CHALLENGES.get(eq["id"], PlaceholderChallenge)(eq)
