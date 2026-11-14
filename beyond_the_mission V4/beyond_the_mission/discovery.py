"""Equipment discovery: Ghost Robot encounters and the recovery sequence
(choice -> challenge -> Memory Capsule -> archive insertion -> cutscene)."""
import math
import random
import pygame
from settings import SCREEN_W, SCREEN_H, CYAN, TEXT
import sprites
import ui
import puzzle
from ghost import GhostRobot
from story_data import EQUIPMENT

INSERT_TIME = 1.4   # seconds for the capsule-into-archive animation


class EncounterManager:
    """Spawns Ghost Robots according to progress (strict newest-to-oldest)."""

    def __init__(self, progress, on_dialogue_end):
        self.progress = progress
        self.on_dialogue_end = on_dialogue_end   # called with equipment dict
        self.robots = {}
        self.refresh()

    def refresh(self):
        for eq in EQUIPMENT:
            eid = eq["id"]
            if not eq["implemented"] or eid in self.robots:
                continue
            if self.progress.is_available(eid) or self.progress.is_recovered(eid):
                ox, oy = eq.get("ghost_offset", (80, 50))
                robot = GhostRobot(eq, eq["site"][0] + ox, eq["site"][1] + oy)
                robot.on_end = lambda eq=eq: self.on_dialogue_end(eq)
                self.robots[eid] = robot
        for eid, robot in self.robots.items():     # lines depend on progress
            eq = robot.eq
            robot.lines = eq["thanks_lines"] if self.progress.is_recovered(eid) else eq["intro_lines"]

    @property
    def interactables(self):
        return list(self.robots.values())


class EncounterScene:
    """Full-screen story panels. Finishes by calling on_finish(completed)."""

    def __init__(self, eq, progress, on_finish):
        self.eq, self.progress, self.on_finish = eq, progress, on_finish
        self.t = 0.0
        self.challenge = None
        self.buttons = None
        self.dim = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self.dim.fill((0, 0, 0, 150))
        rng = random.Random(5)
        self.stars = [(rng.randrange(SCREEN_W), rng.randrange(SCREEN_H), rng.randint(80, 220)) for _ in range(90)]
        self.capsule = sprites.draw_capsule()
        self.go("choice")

    def go(self, phase):
        self.phase, self.t = phase, 0.0
        if phase == "choice":
            self.buttons = ui.ButtonRow(["Begin Challenge", "Not Yet"], 330)
        elif phase == "minigame":
            self.challenge = puzzle.make_challenge(self.eq)
        elif phase == "capsule":
            self.buttons = ui.ButtonRow(["Insert into Archive"], 410, w=300)
        elif phase == "insert":
            if not self.progress.recover(self.eq["id"]):   # blocks duplicates / skipping ahead
                self.on_finish(False)
                return
            self.buttons = ui.ButtonRow(["Continue"], 405)
        elif phase == "cutscene":
            self.buttons = ui.ButtonRow(["Skip"], SCREEN_H - 62)

    def handle_event(self, e):
        if self.phase == "choice":
            i = self.buttons.handle_event(e)
            if i == 0:
                self.go("minigame")
            elif i == 1:
                self.on_finish(False)
        elif self.phase == "minigame":
            if self.challenge.handle_event(e) == "done":
                self.go("capsule")
        elif self.phase == "capsule":
            if self.buttons.handle_event(e) == 0:
                self.go("insert")
        elif self.phase == "insert":
            if self.t >= INSERT_TIME and self.buttons.handle_event(e) == 0:
                self.go("cutscene")
        elif self.phase == "cutscene":
            if self.buttons.handle_event(e) == 0:
                self.on_finish(True)

    def update(self, dt):
        self.t += dt
        if self.phase == "minigame":
            self.challenge.update(dt)

    # ---------------------------------------------------------------- drawing
    def draw(self, surf):
        if self.phase == "cutscene":
            return self._draw_cutscene(surf)
        surf.blit(self.dim, (0, 0))
        if self.phase == "choice":
            r = ui.center_panel(surf, 640, 260)
            ui.draw_title(surf, "Recover Memories", r.y + 26)
            ui.draw_wrapped(surf, f"{self.eq['ghost_name']}'s memories are scattered. "
                                  "Begin the challenge to recover them?", 32, r.inflate(-60, 0), r.y + 100)
            self.buttons.draw(surf)
        elif self.phase == "minigame":
            self.challenge.draw(surf)
        elif self.phase == "capsule":
            r = ui.center_panel(surf, 640, 420)
            ui.draw_title(surf, self.eq["capsule_title"], r.y + 22, 46)
            bob = math.sin(self.t * 2.5) * 6
            cx, cy = SCREEN_W // 2, r.y + 150 + int(bob)
            surf.blit(sprites.glow(100, 5), (cx - 100, cy - 100), special_flags=pygame.BLEND_RGB_ADD)
            surf.blit(self.capsule, self.capsule.get_rect(center=(cx, cy)))
            ui.draw_wrapped(surf, self.eq["capsule_blurb"], 30, r.inflate(-60, 0), r.y + 240)
            self.buttons.draw(surf)
        elif self.phase == "insert":
            self._draw_insert(surf)

    def _draw_insert(self, surf):
        panel = ui.center_panel(surf, 820, 400)
        done = self.t >= INSERT_TIME
        ids = self.progress.recovered
        shown = ids if done else [i for i in ids if i != self.eq["id"]]
        ui.draw_archive(surf, panel, shown, self.progress.archive.integrity if done
                        else max(0, len(shown)) / ui.SLOTS)
        slot = ui.archive_slot_rect(panel, [e["id"] for e in EQUIPMENT].index(self.eq["id"]))
        if not done:
            k = self.t / INSERT_TIME
            k = k * k * (3 - 2 * k)                         # smoothstep
            sx, sy = SCREEN_W // 2, panel.y - 20
            x = sx + (slot.centerx - sx) * k
            y = sy + (slot.centery - 10 - sy) * k
            scale = 1.0 - 0.65 * k
            img = pygame.transform.scale(self.capsule, (int(80 * scale), int(136 * scale)))
            surf.blit(sprites.glow(60, 5), (int(x) - 60, int(y) - 60), special_flags=pygame.BLEND_RGB_ADD)
            surf.blit(img, img.get_rect(center=(int(x), int(y))))
        else:
            flash = max(0.0, 1 - (self.t - INSERT_TIME) * 2)
            if flash > 0:
                surf.blit(sprites.glow(70, int(2 + flash * 7)), (slot.centerx - 70, slot.centery - 70),
                          special_flags=pygame.BLEND_RGB_ADD)
            ui.draw_wrapped(surf, "Ghost Rover: Memory fragment received... Archive integrity improving.",
                            30, panel.inflate(-80, 0), panel.y + 262, CYAN)
            self.buttons.draw(surf)

    def _draw_cutscene(self, surf):
        surf.fill((8, 6, 14))
        for x, y, b in self.stars:
            surf.set_at((x, y), (b, b, b))
        pygame.draw.circle(surf, (96, 40, 28), (SCREEN_W // 2, SCREEN_H + 560), 700)   # Mars horizon
        pygame.draw.circle(surf, (150, 70, 42), (SCREEN_W // 2, SCREEN_H + 575), 700)
        art = sprites.GHOST_ROBOT_ART[self.eq["id"]](int(self.t * 12) % 2)
        art = pygame.transform.scale(art, (art.get_width() * 3, art.get_height() * 3))
        cx, cy = SCREEN_W // 2, 255 + int(math.sin(self.t * 2) * 8)
        surf.blit(sprites.glow(150, 5, self.eq["tint"]), (cx - 150, cy - 150), special_flags=pygame.BLEND_RGB_ADD)
        surf.blit(art, art.get_rect(center=(cx, cy)))
        pygame.draw.rect(surf, (0, 0, 0), (0, 0, SCREEN_W, 76))               # letterbox
        pygame.draw.rect(surf, (0, 0, 0), (0, SCREEN_H - 76, SCREEN_W, 76))
        ui.draw_title(surf, "Memory Reconstruction", 14, 50)
        ui.draw_title(surf, self.eq["name"], 90, 44, TEXT)
        ui.draw_wrapped(surf, self.eq["cutscene_text"], 32, pygame.Rect(120, 0, SCREEN_W - 240, 0), 370, TEXT)
        self.buttons.draw(surf)
        fade = max(0, 255 - int(self.t * 400))
        if fade:
            f = pygame.Surface((SCREEN_W, SCREEN_H))
            f.set_alpha(fade)
            surf.blit(f, (0, 0))
