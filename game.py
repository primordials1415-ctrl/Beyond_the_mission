import math
import random
import pygame
from settings import *
import sprites
import ui
import story_data
from player import Player
from ghost import Ghost
from world import World
from interaction import InteractionSystem
from journal import StoryProgress
from discovery import EncounterManager, EncounterScene
from intro import Intro


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Beyond the Mission - Prototype")
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock = pygame.time.Clock()
        self.world = World()
        self.vignette = sprites.make_vignette(SCREEN_W, SCREEN_H)
        rng = random.Random(3)
        self.stars = [(rng.randrange(SCREEN_W), rng.randrange(SCREEN_H), rng.choice((1, 1, 2)),
                       rng.randint(90, 220)) for _ in range(140)]
        self.menu = ui.Menu("BEYOND THE MISSION", [("Play", "play"), ("Exit", "exit")])
        self.pause_menu = ui.Menu("PAUSED", [("Resume", "resume"), ("Main Menu", "menu")])
        self.state = "menu"      # menu | intro | play | pause | scene
        self.running = True
        self.time = 0.0
        self.new_game()

    def new_game(self):
        self.progress = StoryProgress()
        self.scene = None
        self.toast = None            # [text, age]
        self.player = Player(*self.world.spawn)
        self.ghost = Ghost(*self.world.ghost_start)
        self.ghost.following = True  # Ghost Rover accompanies the player
        self.interaction = InteractionSystem()
        self.encounters = EncounterManager(self.progress, self.start_encounter)
        self.cam = self._cam_target()

    def start_story(self):
        self.interaction.start_lines(story_data.INTRO_LINES, on_end=self._intro_done)

    def _intro_finished(self):
        """Cinematic intro ended (or was skipped): begin normal gameplay."""
        self.state = "play"
        self.start_story()

    def _intro_done(self):
        self.progress.signal_detected = True

    @property
    def interactables(self):
        return [self.ghost] + self.world.interactables + self.encounters.interactables

    # ---------------------------------------------------------- story flow
    def start_encounter(self, eq):
        """Called when a Ghost Robot's dialogue ends."""
        if self.scene or self.progress.is_recovered(eq["id"]) or not self.progress.is_available(eq["id"]):
            return
        self.scene = EncounterScene(eq, self.progress, lambda done, eq=eq: self._scene_done(eq, done))
        self.state = "scene"

    def _scene_done(self, eq, completed):
        self.scene = None
        self.state = "play"
        if completed:
            self.encounters.refresh()
            self.toast = ["Memory Successfully Recovered!", 0.0]
            self.interaction.start_lines(eq["recovery_lines"])

    def _cam_target(self):
        t = pygame.Vector2(self.player.pos.x - SCREEN_W / 2, self.player.pos.y - 20 - SCREEN_H / 2)
        t.x = max(0, min(MAP_W - SCREEN_W, t.x))
        t.y = max(0, min(MAP_H - SCREEN_H, t.y))
        return t

    def read_input(self):
        k = pygame.key.get_pressed()
        x = int(k[pygame.K_d] or k[pygame.K_RIGHT]) - int(k[pygame.K_a] or k[pygame.K_LEFT])
        y = int(k[pygame.K_s] or k[pygame.K_DOWN]) - int(k[pygame.K_w] or k[pygame.K_UP])
        return pygame.Vector2(x, y)

    # ------------------------------------------------------------ events
    def handle_event(self, e):
        if e.type == pygame.QUIT:
            self.running = False
        elif self.state == "menu":
            action = self.menu.handle_event(e)
            if action == "play":
                self.new_game()
                self.intro = Intro(self.world, self.player, self.ghost, self.cam, self._intro_finished)
                self.state = "intro"
            elif action == "exit":
                self.running = False
        elif self.state == "intro":
            self.intro.handle_event(e)
        elif self.state == "play":
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self.state = "pause"
                self.pause_menu.sel = 0
            else:
                self.interaction.handle_event(e)
        elif self.state == "scene":
            self.scene.handle_event(e)
        elif self.state == "pause":
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self.state = "play"
                return
            action = self.pause_menu.handle_event(e)
            if action == "resume":
                self.state = "play"
            elif action == "menu":
                self.state = "menu"

    # ------------------------------------------------------------ update
    def update(self, dt):
        self.time += dt
        if self.toast:
            self.toast[1] += dt
            if self.toast[1] > 4:
                self.toast = None
        if self.state == "intro":
            self.intro.update(dt)
            return
        if self.state == "scene":
            self.scene.update(dt)
            return
        if self.state != "play":
            return
        move = pygame.Vector2() if self.interaction.in_dialogue else self.read_input()
        self.player.update(dt, move, self.world.colliders)
        talking_to_ghost = self.interaction.active is self.ghost
        self.ghost.update(dt, self.player.pos, frozen=talking_to_ghost)
        for robot in self.encounters.interactables:
            robot.update(dt)
        if not self.interaction.in_dialogue:
            self.ghost.lines = story_data.rover_lines(self.progress)
        self.interaction.update(self.player.pos, self.interactables)
        self.cam += (self._cam_target() - self.cam) * min(1.0, 8 * dt)

    # -------------------------------------------------------------- draw
    def _signal_site(self):
        cur = self.progress.current()
        if self.progress.signal_detected and cur and cur["implemented"]:
            return cur["site"]
        return None

    def draw_world(self):
        cam = pygame.Vector2(int(self.cam.x), int(self.cam.y))
        self.world.draw_ground(self.screen, cam)
        site = self._signal_site()
        if site:
            self.world.draw_signal(self.screen, cam, site, self.time)
        drawables = self.world.props + [self.player, self.ghost] + self.encounters.interactables
        for d in sorted(drawables, key=lambda d: d.sort_y):
            d.draw(self.screen, cam)
        self.screen.blit(self.vignette, (0, 0))
        if site:
            self._draw_signal_arrow(site, cam)
        t = self.interaction.target
        if t:
            ui.draw_prompt(self.screen, (int(t.pos.x - cam.x), int(t.pos.y - t.prompt_offset - cam.y)), t.prompt)
        if self.interaction.in_dialogue:
            speaker, text = self.interaction.current
            ui.draw_dialogue(self.screen, speaker, text)

    def _draw_signal_arrow(self, site, cam):
        dx, dy = site[0] - cam.x - SCREEN_W / 2, site[1] - cam.y - SCREEN_H / 2
        if abs(dx) < SCREEN_W / 2 - 50 and abs(dy) < SCREEN_H / 2 - 50:
            return   # signal is on screen
        k = min((SCREEN_W / 2 - 40) / abs(dx) if dx else 1e9, (SCREEN_H / 2 - 40) / abs(dy) if dy else 1e9)
        px, py = SCREEN_W / 2 + dx * k, SCREEN_H / 2 + dy * k
        a = math.atan2(dy, dx)
        pts = [(px + math.cos(a) * 14, py + math.sin(a) * 14),
               (px + math.cos(a + 2.5) * 12, py + math.sin(a + 2.5) * 12),
               (px + math.cos(a - 2.5) * 12, py + math.sin(a - 2.5) * 12)]
        pygame.draw.polygon(self.screen, CYAN, pts)

    def draw_menu_bg(self):
        s = self.screen
        s.fill((14, 7, 10))
        for x, y, r, b in self.stars:
            pygame.draw.circle(s, (b, b, b), (x, y), r)
        pygame.draw.circle(s, (120, 48, 30), (SCREEN_W // 2, SCREEN_H + 380), 560)
        pygame.draw.circle(s, (170, 78, 44), (SCREEN_W // 2, SCREEN_H + 400), 540)

    def draw(self):
        if self.state == "menu":
            self.draw_menu_bg()
            self.menu.draw(self.screen, 90)
            return
        if self.state == "intro":
            self.intro.draw(self.screen)
            return
        self.draw_world()
        if self.state == "scene":
            self.scene.draw(self.screen)
            return
        ui.draw_hud(self.screen, story_data.objective(self.progress))
        if self.toast:
            ui.draw_toast(self.screen, self.toast[0], self.toast[1])
        if self.state == "pause":
            dim = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 150))
            self.screen.blit(dim, (0, 0))
            ui.draw_panel(self.screen, (SCREEN_W // 2 - 190, 110, 380, 300), 235)
            self.pause_menu.draw(self.screen, 140)

    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000, 0.05)
            for e in pygame.event.get():
                self.handle_event(e)
            self.update(dt)
            self.draw()
            pygame.display.flip()
        pygame.quit()
